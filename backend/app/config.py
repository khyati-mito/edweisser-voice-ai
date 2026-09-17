import os

from dotenv import load_dotenv

load_dotenv()

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Where complaint escalations get emailed. Real delivery doesn't happen yet
# (see tools/email_tool.py) so any placeholder is fine until Gmail creds land.
COMPLAINT_NOTIFY_EMAIL = os.environ.get("COMPLAINT_NOTIFY_EMAIL", "complaints-demo@example.com")
