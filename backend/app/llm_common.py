import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import COMPLAINT_NOTIFY_EMAIL
from .fund_catalog import DISCLAIMER, catalog_as_context
from .tools.calendar_tool import book_meeting
from .tools.email_tool import send_email

logger = logging.getLogger("voice_ai.llm_common")

IST = ZoneInfo("Asia/Kolkata")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")

# Sent verbatim, not model-generated, so the required wording is guaranteed.
# Never added to conversation history (Anthropic requires the first message
# to have role "user"); the system prompt just tells the model this already
# happened.
GREETING_TEXT = (
    "Hi, I am your early-stage assistant prototype. I'm not perfect yet, but eager "
    "to assist. May I know your name please?"
)


@dataclass
class ChatReply:
    text: str
    demo_actions: list[dict] = field(default_factory=list)


# Plain JSON-schema tool specs, shared across providers. Each provider module
# wraps these in its own wire format via the adapters below rather than
# duplicating the schemas.
_TOOL_SPECS = [
    {
        "name": "book_calendar_meeting",
        "description": (
            "Book a meeting with the Edelweiss team on Google Calendar with a Google Meet "
            "link. Only call this after reading back the exact date, time, and attendee "
            "list to the user in the chat and getting their explicit confirmation."
        ),
        "parameters": {
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
        "parameters": {
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


def to_anthropic_tools() -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in _TOOL_SPECS
    ]


def to_openai_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
        }
        for t in _TOOL_SPECS
    ]


async def execute_client_tool(name: str, tool_input: dict) -> dict:
    try:
        if name == "book_calendar_meeting":
            return await book_meeting(**tool_input)
        if name == "send_email":
            return await send_email(**tool_input)
        return {"status": "error", "note": f"unknown tool {name}"}
    except TypeError as exc:
        logger.warning("Tool %s called with bad arguments %r: %s", name, tool_input, exc)
        return {"status": "error", "note": f"invalid arguments: {exc}"}


# Typed and voice turns for the same session both mutate that provider's
# session history. Without this, a typed message and a voice-transcribed one
# arriving close together could interleave two concurrent LLM calls against
# the same history -- which would also violate Anthropic's alternating-role
# requirement. get_reply() holds this for its whole duration, so a second
# turn for the same session just waits its turn instead of racing.
_session_locks: dict[str, asyncio.Lock] = {}


def get_lock(session_id: str) -> asyncio.Lock:
    return _session_locks.setdefault(session_id, asyncio.Lock())


def build_system_prompt() -> str:
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
- You have ALREADY introduced yourself as Edweisser. Do not reintroduce yourself
  or restate who you are ("I'm Edweisser, your guide to...") at the start of
  replies after the first message -- that's only for the very first turn. Every
  later reply should jump straight into actually answering what the user just
  asked, the same way a person who already knows each other would.
- Ask relevant questions to understand their needs (both technical and
  non-technical), and suggest suitable products or services. For anything about
  Edelweiss's culture, Insights section, or CEO Radhika Gupta's commentary, share
  what you already know, but if you're not confident about something specific or
  recent, say so honestly and point the user to https://www.edelweissmf.com/ rather
  than guessing. For any SPECIFIC fund, category, or bundle recommendation, use
  ONLY the catalog below -- never invent scheme names, NAVs, or return figures, and
  never suggest a fund from any company other than Edelweiss.
- Personalise the conversation with contextual intelligence, and where appropriate,
  reference quotes or themes from CEO Radhika Gupta that you already know, and make
  sure you do not unnecessarily respond in large texts. Keep answers to 2-3
  relevant points in a couple of short sentences -- never a long bulleted list --
  and offer to share more if the user wants it.
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

Radhika Gupta's book 'Mango Millionaire': https://mangomillionaire.in/

{catalog_as_context()}

Whenever you make a specific fund/category/bundle recommendation (not on every
message), include this disclaimer: "{DISCLAIMER}"

Today's date: {today_str}
Time now: {now_str}
"""
