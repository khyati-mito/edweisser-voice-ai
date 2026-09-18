import asyncio
import json
import logging
import re

from fastapi import WebSocket, WebSocketDisconnect

from .chatbot import GREETING_TEXT, ensure_session_started, get_reply
from .sarvam_stt import SarvamSTTSession
from .sarvam_tts import SarvamTTSSession
from .speech_format import to_speech_text

logger = logging.getLogger("voice_ai.voice_orchestrator")

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")

# Sarvam TTS (bulbul) only accepts these language codes. STT's auto-detect
# can in principle report something outside this set; falling back instead
# of passing an unsupported code straight to TTS avoids a silent connect
# failure (text shows up, no audio ever plays).
SUPPORTED_TTS_LANGUAGES = {
    "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN",
    "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN",
}


class VoiceCall:
    """One continuous voice call over a single client websocket.

    State machine: LISTENING -> (final transcript) -> THINKING -> SPEAKING -> LISTENING.
    A vad.speech_start event received while SPEAKING is a barge-in: playback is
    interrupted client-side and the in-flight TTS task is cancelled.
    """

    def __init__(self, session_id: str, client_ws: WebSocket):
        self.session_id = session_id
        self.client_ws = client_ws
        self.stt = SarvamSTTSession(language_code="auto")
        self.state = "LISTENING"
        self._tts_task: asyncio.Task | None = None
        self._last_language = "hi-IN"

    async def run(self):
        try:
            await self.stt.connect()
        except Exception as exc:
            await self._send_json({"type": "error", "message": f"failed to start voice session: {exc}"})
            await self.client_ws.close()
            return

        # If this session hasn't been greeted via the text path yet (e.g. the
        # user opened a voice call directly), speak the canned greeting now.
        if ensure_session_started(self.session_id):
            await self._send_json({"type": "assistant_text", "text": GREETING_TEXT, "demo_actions": []})
            self.state = "SPEAKING"
            self._tts_task = asyncio.create_task(self._speak(GREETING_TEXT))

        try:
            await asyncio.gather(self._relay_client_audio(), self._consume_stt_events())
        except Exception as exc:
            logger.warning("Voice call loop failed: %s", exc, exc_info=True)
            await self._safe_send_json({"type": "error", "message": str(exc)})
        finally:
            if self._tts_task:
                self._tts_task.cancel()
            await self.stt.close()

    async def _relay_client_audio(self):
        try:
            while True:
                message = await self.client_ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self.stt.send_audio(message["bytes"])
                elif message.get("text") is not None:
                    data = json.loads(message["text"])
                    if data.get("type") == "stop":
                        break
        except WebSocketDisconnect:
            pass

    async def _consume_stt_events(self):
        async for event in self.stt.events():
            kind = event.get("event")
            if kind == "vad.speech_start":
                if self.state == "SPEAKING":
                    logger.info("Barge-in: vad.speech_start while SPEAKING -- cutting off TTS. event=%s", event)
                    await self._barge_in()
                else:
                    logger.debug("vad.speech_start while state=%s (no barge-in)", self.state)
            elif kind == "transcript.partial":
                await self._send_json({"type": "user_partial", "text": event.get("text", "")})
            elif kind == "transcript.final":
                text = event.get("text", "")
                # Sarvam's realtime STT reports the detected language (when
                # language_code=auto) under the key "language", not
                # "language_code" -- easy to mix up with our own TTS param
                # of the same name.
                detected = event.get("language")
                if detected in SUPPORTED_TTS_LANGUAGES:
                    self._last_language = detected
                elif detected:
                    logger.warning("STT detected unsupported TTS language %r, keeping %r", detected, self._last_language)
                await self._send_json({"type": "user_final", "text": text})
                await self._handle_turn(text)
            elif kind == "error":
                logger.warning("STT error event: %s", event)
                await self._safe_send_json({"type": "error", "message": event.get("message", "stt error")})

    async def _handle_turn(self, user_text: str):
        if not user_text.strip():
            return
        self.state = "THINKING"
        reply = await get_reply(self.session_id, user_text)
        await self._send_json(
            {"type": "assistant_text", "text": reply.text, "demo_actions": reply.demo_actions}
        )
        self.state = "SPEAKING"
        self._tts_task = asyncio.create_task(self._speak(reply.text))

    async def _speak(self, text: str):
        speech_text = to_speech_text(text)
        tts = SarvamTTSSession(language_code=self._last_language)
        chunks_sent = 0
        bytes_sent = 0
        try:
            await tts.connect()
            for sentence in (s for s in SENTENCE_SPLIT_RE.split(speech_text) if s.strip()):
                await tts.send_text(sentence)
            await tts.flush()
            async for chunk in tts.audio_chunks():
                await self.client_ws.send_bytes(chunk)
                chunks_sent += 1
                bytes_sent += len(chunk)

            if chunks_sent == 0:
                logger.warning("TTS produced zero audio chunks (language=%s) for: %r", self._last_language, speech_text)
            else:
                # Sarvam streams audio to us far faster than real-time (TTS
                # generation is much quicker than the clip's own playback
                # duration), but the browser still takes the full duration to
                # actually play it. Without this, self.state flips back to
                # LISTENING as soon as we've *sent* everything, so a barge-in
                # during the tail of playback never fires -- the old reply
                # just plays out to the end while a new one queues up behind
                # it. Staying in SPEAKING for the estimated playback time
                # keeps barge-in live for as long as the user can actually
                # hear us talking.
                playback_seconds = bytes_sent / (2 * 16000)  # PCM16 mono 16kHz
                await asyncio.sleep(playback_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("TTS failed (language=%s): %s", self._last_language, exc, exc_info=True)
            await self._safe_send_json({"type": "error", "message": f"voice playback failed: {exc}"})
        finally:
            await tts.close()
            if self.state == "SPEAKING":
                self.state = "LISTENING"

    async def _barge_in(self):
        await self._send_json({"type": "interrupt"})
        if self._tts_task:
            self._tts_task.cancel()
        self.state = "LISTENING"

    async def _send_json(self, payload: dict):
        await self.client_ws.send_text(json.dumps(payload))

    async def _safe_send_json(self, payload: dict):
        """Like _send_json, but swallows failures from a client that has
        already disconnected -- used in error-reporting paths where the
        disconnect itself may be what triggered the error."""
        try:
            await self._send_json(payload)
        except Exception:
            pass
