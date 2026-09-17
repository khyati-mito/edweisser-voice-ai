import asyncio
import base64
import json

import websockets
from websockets.exceptions import ConnectionClosed

from .config import SARVAM_API_KEY

TTS_URL = "wss://api.sarvam.ai/text-to-speech/ws"

# How long to wait for the next websocket message before giving up on this
# utterance. Without send_completion_event=true, Sarvam doesn't reliably send
# a "final" event to mark the end of an utterance (confirmed empirically --
# audio chunks arrive fine, but the connection then goes silent with no
# closing signal), which made the old code hang forever waiting for one.
# This timeout is a safety net on top of requesting that event explicitly.
IDLE_TIMEOUT_SECONDS = 15.0


class SarvamTTSSession:
    """Wraps Sarvam's streaming TTS websocket (bulbul:v3).

    Text -> send_text() (call flush() once the turn's text is fully sent).
    PCM16 audio chunks -> audio_chunks().
    """

    def __init__(self, language_code: str = "hi-IN", speaker: str = "shubh", model: str = "bulbul:v3"):
        self._language_code = language_code
        self._speaker = speaker
        self._model = model
        self._ws = None

    async def connect(self):
        url = f"{TTS_URL}?model={self._model}&send_completion_event=true"
        self._ws = await websockets.connect(
            url,
            extra_headers={"Api-Subscription-Key": SARVAM_API_KEY},
        )
        config = {
            "type": "config",
            "data": {
                "language_code": self._language_code,
                "speaker": self._speaker,
                "model": self._model,
                "speech_sample_rate": "16000",
                "output_audio_codec": "linear16",
                "pace": 1.0,
            },
        }
        await self._ws.send(json.dumps(config))

    async def send_text(self, text: str):
        await self._ws.send(json.dumps({"type": "text", "data": {"text": text}}))

    async def flush(self):
        await self._ws.send(json.dumps({"type": "flush"}))

    async def audio_chunks(self):
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=IDLE_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, ConnectionClosed):
                return
            msg = json.loads(raw)
            msg_type = msg.get("type")
            if msg_type == "audio":
                yield base64.b64decode(msg["data"]["audio"])
            elif msg_type == "event" and msg.get("data", {}).get("event_type") == "final":
                return
            elif msg_type == "error":
                return

    async def close(self):
        if self._ws is not None:
            await self._ws.close()
