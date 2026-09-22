from .config import LLM_PROVIDER
from .llm_common import GREETING_TEXT, ChatReply

if LLM_PROVIDER == "openrouter":
    from .llm_openrouter import get_reply
else:
    from .llm_anthropic import get_reply

__all__ = ["GREETING_TEXT", "ChatReply", "get_reply", "ensure_session_started"]

# Tracks which sessions have already been greeted -- independent of
# conversation history/content, so it doesn't belong to either provider
# module. A session is "started" the first time either the typed /chat/start
# endpoint or a voice call touches it.
_started_sessions: set[str] = set()


def ensure_session_started(session_id: str) -> bool:
    """Returns True the first time a given session_id is seen, False on
    every call after that."""
    if session_id in _started_sessions:
        return False
    _started_sessions.add(session_id)
    return True
