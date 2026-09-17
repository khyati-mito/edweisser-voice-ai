# Voice AI POC — Edelweiss Fund Advisor

A chatbot (mutual fund advisor scoped to Edelweiss Mutual Fund) with a voice add-on
built on Sarvam's realtime STT (`saaras:v3-realtime`) and streaming TTS
(`bulbul:v3`). Voice is purely an input/output layer: typed messages and spoken
messages both flow through the same `chatbot.get_reply()` function and land in the
same chat log.

Continuous, real-time call experience: always-listening while the call is open,
live partial transcripts, and barge-in (speaking while the assistant is talking
stops playback immediately). Language auto-detected across Hindi + other Indian
languages supported by Sarvam.

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in SARVAM_API_KEY and ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Runs on `http://localhost:8000`.

### Frontend

Needs Node 18+ (the scaffold was built with Node 22 via `nvm use 22`).

```bash
cd frontend
npm install
cp .env.example .env   # defaults already point at localhost:8000
npm run dev
```

Open the printed local URL. Voice requires mic permission and works best served
over `localhost` or HTTPS.

## How it fits together

- `backend/app/chatbot.py` — the advisor logic (Claude call + Edelweiss fund
  catalog grounding + disclaimer). This is the one place you'd swap in a real
  production agent later.
- `backend/app/sarvam_stt.py` / `sarvam_tts.py` — thin wrappers around Sarvam's
  realtime websockets.
- `backend/app/voice_orchestrator.py` — bridges one browser call: mic audio → STT
  → chatbot → TTS → audio back, plus barge-in handling.
- `backend/app/main.py` — `POST /chat` (typed path) and `WS /voice` (voice path),
  both backed by the same chatbot function.
- `frontend/src/App.jsx` — one shared chat log; a text box and a mic/call button
  both write into it.
- `frontend/src/hooks/useVoiceCall.js` — owns the mic capture, the `/voice`
  websocket, and audio playback for one call.

## Known limitations (POC-level)

- Fund data (`backend/app/fund_catalog.py`) is a small static, illustrative
  dataset, not live scheme/NAV data from edelweissmf.com.
- Conversation history is in-memory per backend process — restarting the
  backend clears it.
- No auth — anyone who can reach the backend can use `/chat` and `/voice`.
