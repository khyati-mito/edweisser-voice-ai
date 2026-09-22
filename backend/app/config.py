import os

from dotenv import load_dotenv

load_dotenv()

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Which chat backend to use: "anthropic" (default) or "openrouter". Lets the
# whole app switch providers via one env var without code changes.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

# Where complaint escalations get emailed. Real delivery doesn't happen yet
# (see tools/email_tool.py) so any placeholder is fine until Gmail creds land.
COMPLAINT_NOTIFY_EMAIL = os.environ.get("COMPLAINT_NOTIFY_EMAIL", "complaints-demo@example.com")
