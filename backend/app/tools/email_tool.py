import logging

logger = logging.getLogger("voice_ai.email_tool")


# TODO: swap for a real Gmail API call once OAuth credentials for the
# dedicated test account arrive.
async def send_email(to: str, subject: str, body: str) -> dict:
    logger.info("[DEMO] Simulated email: to=%s subject=%r body=%r", to, subject, body)

    return {
        "status": "simulated",
        "to": to,
        "subject": subject,
        "note": "DEMO MODE: no real email was sent.",
    }
