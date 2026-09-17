import base64
import json

import websockets
from websockets.exceptions import ConnectionClosed

from .config import SARVAM_API_KEY

STT_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"


class SarvamSTTSession:
    """Wraps Sarvam's realtime STT websocket (saaras:v3-realtime).

    Client audio -> send_audio(). Server events (partial/final transcripts,
    VAD boundaries) -> events().
    """

    def __init__(self, language_code: str = "auto", model: str = "saaras:v3-realtime"):
        self._language_code = language_code
        self._model = model
        self._ws = None

    async def connect(self):
        url = (
            f"{STT_URL}?language_code={self._language_code}"
            f"&model={self._model}&stream_type=balanced"
            f"&encoding=linear16&sample_rate=16000&endpointing=vad"
        )
        self._ws = await websockets.connect(
            url,
            extra_headers={"API-SUBSCRIPTION-KEY": SARVAM_API_KEY},
        )

    async def send_audio(self, pcm_bytes: bytes):
        payload = {"event": "audio_input", "audio": base64.b64encode(pcm_bytes).decode()}
        await self._ws.send(json.dumps(payload))

    async def events(self):
        async for raw in self._ws:
            yield json.loads(raw)

    async def close(self):
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"event": "end"}))
        except ConnectionClosed:
            pass
        await self._ws.close()
