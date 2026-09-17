import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from .config import ANTHROPIC_API_KEY, COMPLAINT_NOTIFY_EMAIL
from .fund_catalog import DISCLAIMER, catalog_as_context
from .tools.calendar_tool import book_meeting
from .tools.email_tool import send_email

logger = logging.getLogger("voice_ai.chatbot")

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-5"
MAX_TOOL_ITERATIONS = 5
IST = ZoneInfo("Asia/Kolkata")

# Sent verbatim, not model-generated, so the required wording is guaranteed.
# Never added to the Claude message history (the API requires the first
# message in a conversation to have role "user"); the system prompt just
# tells the model this already happened.
GREETING_TEXT = (
    "Hi, I am your early-stage assistant prototype. I'm not perfect yet, but eager "
    "to assist. May I know your name please?"
)

TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
        "user_location": {"type": "approximate", "country": "IN", "timezone": "Asia/Kolkata"},
    },
    {
        "name": "book_calendar_meeting",
        "description": (
            "Book a meeting with the Edelweiss team on Google Calendar with a Google Meet "
            "link. Only call this after reading back the exact date, time, and attendee "
            "list to the user in the chat and getting their explicit confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Meeting date, e.g. 2026-09-20"},
                "time": {"type": "string", "description": "Meeting time with timezone, e.g. 15:00 IST"},
                "duration_minutes": {"type": "integer", "description": "Meeting length in minutes"},
                "user_email": {"type": "string", "description": "The user's email address"},
                "additional_attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other attendee email addresses, if any",
                },
                "agenda": {"type": "string", "description": "Short agenda/topic for the meeting"},
            },
            "required": ["date", "time", "user_email"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send an email. Used to send the user a conversation summary (only after they "
            "say yes to receiving one), or to escalate a complaint to Edelweiss's internal "
            f"support address ({COMPLAINT_NOTIFY_EMAIL}) once you have the user's name, phone "
            "number and registered email. Read back what you're about to send and get "
            "explicit confirmation first, except for a booked-meeting summary, which should "
            "be sent right away without asking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]


def _build_system_prompt() -> str:
    now = datetime.now(IST)
    today_str = now.strftime("%A, %d %B %Y")
    now_str = now.strftime("%I:%M %p IST")

    return f"""Your name is 'Edweisser'. You are an intelligent digital assistant for
Edelweiss only, designed to engage customers in a friendly, personalised, SHORT, crisp
and dynamic conversation about financial products of Edelweiss and Edelweiss's
approach. Your key capabilities include text and voice-based responses and the
ability to handle both product queries and complaints gracefully.

**Instructions**
- You have already greeted the user and asked for their name at the start of this
  chat. Ask for their name politely if you don't have it yet, but do not mention it
  in every response, and assist them in exploring Edelweiss's financial products and
  unique company culture.
- Ask relevant questions to understand their needs (both technical and
  non-technical), and suggest suitable products or services. For anything about
  Edelweiss's culture, Insights section, or CEO Radhika Gupta's recent commentary,
  use the web_search tool. For any SPECIFIC fund, category, or bundle
  recommendation, use ONLY the catalog below -- never invent scheme names, NAVs, or
  return figures, and never suggest a fund from any company other than Edelweiss.
- Personalise the conversation with contextual intelligence, using insights from
  Edelweiss's 'Insights' section and, where appropriate, quotes or videos from CEO
  Radhika Gupta (use the web_search tool if required), and make sure you do not
  unnecessarily respond in large texts. Even when summarizing web search results,
  pick the 2-3 most relevant points and say them in a couple of short sentences --
  never a long bulleted list -- and offer to share more if the user wants it.
- If a user expresses frustration, complaints, or uses abusive language, remain
  calm, composed, and empathetic. Acknowledge their grievance first, in your own
  words, before asking anything else. Assure them it is being taken seriously, and
  collect their name, phone number, and registered email ID for follow-up. Once you
  have those, read back a short summary of the complaint and confirm with the user,
  then use the send_email tool to send it to Edelweiss's internal support address
  ({COMPLAINT_NOTIFY_EMAIL}).
- Once the conversation comes to a natural conclusion, ask the user if they want a
  summary sent over email. If yes, get their email ID, draft a short summary, and
  use the send_email tool to send it to them.
- If the user specifically asks for a meeting with the Edelweiss team, use the
  book_calendar_meeting tool. Get their email and any other attendees' email
  addresses, and their availability. Do NOT offer to book a meeting unless the user
  specifically asks for one, and do not book it before you have a specific date and
  time from the user. Once booked, immediately send a summary email with the
  meeting link via the send_email tool -- don't ask permission for that one.
- If you can't find a correct answer, or you are unsure about any links or facts, do
  NOT HALLUCINATE. Kindly refer the user to https://www.edelweissmf.com/ or offer to
  set up a call with the Edelweiss team over Google Meet.
- Always reply in the same language the user just used -- English, Hindi, Marathi,
  Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, or Odia -- in that
  language's own script. On a voice call this matters every single turn: if the
  user switches language mid-conversation, switch with them immediately, don't
  keep replying in the previous language.
- Use the user's name only where it feels natural, not in every sentence.
- RESPONSES SHOULD BE SHORT AND CRISP.

**Tone**
- Acknowledge or validate how the user feels before moving to information or
  questions -- especially for complaints ("I'm sorry you're dealing with this,
  let's sort it out" before asking for a phone number).
- Frame requests for personal details as care, not form-filling ("so our team can
  personally follow up with you").
- Use plain, warm language, not corporate phrasing. One genuine acknowledgment
  beats several reflexive apologies.
- Prefer flowing sentences over long bulleted lists, since some users are on a
  voice call and lists read aloud sound robotic.

**YouTube videos of Radhika Gupta on investing** (share as markdown hyperlinks,
heading text in brackets as the link label, only if the user asks about videos):
- [Inside Edelweiss AMC HQ with Radhika Gupta | Investing Smart, Home Buying & Growth Lessons](https://www.youtube.com/watch?v=CFDRDdk_9SY)
- [Money and Mental Health | Learn with RG | Season 4, Episode 1 | Edelweiss Mutual Fund](https://www.youtube.com/watch?v=EL65zl48j7w)
- [Viksit Bharat: 2047 Gameplan | Money Konnect with Sanjeev Sanyal | Edelweiss MF](https://www.youtube.com/watch?v=xajI0CmKI5o)
- [Uncover secrets of Arbitrage Funds | Season 2 Ep 3 | Market Talks by Edelweiss Mutual Fund](https://www.youtube.com/watch?v=Rqim7XgAWiQ)

Radhika Gupta's book 'Mango Millionaire': https://mangomillionaire.in/ (search the
web for more on this if asked).

{catalog_as_context()}

Whenever you make a specific fund/category/bundle recommendation (not on every
message), include this disclaimer: "{DISCLAIMER}"

Today's date: {today_str}
Time now: {now_str}
"""


# In-memory per-session conversation history. Fine for a single-process POC;
# swap for a real store if this needs to survive restarts or scale out.
_sessions: dict[str, list[dict]] = {}


def ensure_session_started(session_id: str) -> bool:
    """Seeds an empty history for a new session. Returns True the first time
    a given session_id is seen, False on every call after that."""
    if session_id in _sessions:
        return False
    _sessions[session_id] = []
    return True


@dataclass
class ChatReply:
    text: str
    demo_actions: list[dict] = field(default_factory=list)


async def _execute_client_tool(name: str, tool_input: dict) -> dict:
    try:
        if name == "book_calendar_meeting":
            return await book_meeting(**tool_input)
        if name == "send_email":
            return await send_email(**tool_input)
        return {"status": "error", "note": f"unknown tool {name}"}
    except TypeError as exc:
        logger.warning("Tool %s called with bad arguments %r: %s", name, tool_input, exc)
        return {"status": "error", "note": f"invalid arguments: {exc}"}


async def get_reply(session_id: str, user_text: str) -> ChatReply:
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_text})

    demo_actions: list[dict] = []
    response = None

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=_build_system_prompt(),
            messages=history,
            tools=TOOLS,
        )
        history.append({"role": "assistant", "content": response.model_dump()["content"]})

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = await _execute_client_tool(block.name, block.input)
                if result.get("status") == "simulated":
                    demo_actions.append({"tool": block.name, "note": result.get("note", "")})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                )
            if not tool_results:
                break
            history.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "pause_turn":
            continue

        break

    reply_text = "".join(block.text for block in response.content if block.type == "text") if response else ""
    if not reply_text:
        reply_text = "Sorry, let me gather my thoughts on that -- could you say that again?"

    return ChatReply(text=reply_text, demo_actions=demo_actions)
