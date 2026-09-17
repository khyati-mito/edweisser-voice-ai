import logging
import uuid

logger = logging.getLogger("voice_ai.calendar_tool")


# TODO: swap for a real Google Calendar API call once OAuth credentials for
# the dedicated test account arrive. Real version should create an event via
# the Calendar API with conferenceData (Meet link) and the given attendees.
async def book_meeting(
    date: str,
    time: str,
    user_email: str,
    duration_minutes: int = 30,
    additional_attendees: list[str] | None = None,
    agenda: str = "",
) -> dict:
    attendees = [user_email, *(additional_attendees or [])]
    meeting_id = f"demo-{uuid.uuid4().hex[:8]}"
    meet_link = f"https://meet.google.com/{meeting_id}"

    logger.info(
        "[DEMO] Simulated calendar booking: date=%s time=%s duration=%smin attendees=%s agenda=%r",
        date,
        time,
        duration_minutes,
        attendees,
        agenda,
    )

    return {
        "status": "simulated",
        "meeting_id": meeting_id,
        "meet_link": meet_link,
        "date": date,
        "time": time,
        "attendees": attendees,
        "note": "DEMO MODE: no real Google Calendar event was created and no real invite was sent.",
    }
