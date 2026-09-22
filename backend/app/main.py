import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .chatbot import GREETING_TEXT, ensure_session_started, get_reply
from .voice_orchestrator import VoiceCall

_log_handler = logging.StreamHandler()
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_app_logger = logging.getLogger("voice_ai")
_app_logger.setLevel(logging.INFO)
_app_logger.addHandler(_log_handler)
_app_logger.propagate = False

logger = logging.getLogger("voice_ai.main")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    text: str


class StartRequest(BaseModel):
    session_id: str


@app.post("/chat/start")
async def chat_start(req: StartRequest):
    ensure_session_started(req.session_id)
    return {"reply": GREETING_TEXT}


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = await get_reply(req.session_id, req.text)
    except Exception as exc:
        # An uncaught exception's default error response doesn't get the
        # CORSMiddleware's headers applied, which the browser then reports
        # as a confusing CORS failure instead of the real error -- return a
        # normal response instead so the actual problem is visible.
        logger.warning("get_reply failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=502,
            content={
                "reply": "Sorry, I'm having trouble reaching the AI service right now. Please try again in a moment.",
                "demo_actions": [],
                "error": str(exc),
            },
        )
    return {"reply": reply.text, "demo_actions": reply.demo_actions}


@app.websocket("/voice")
async def voice(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id", "default")
    call = VoiceCall(session_id, websocket)
    await call.run()
