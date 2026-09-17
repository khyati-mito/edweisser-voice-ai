import re

# Reply text is written for a chat bubble (markdown links, bullets, bold) but
# TTS must never speak raw URLs or markdown punctuation aloud. This strips
# that formatting down to flowing sentences for the voice path only -- the
# visible chat transcript keeps the original text untouched.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^\s)]+\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_BULLET_RE = re.compile(r"^[ \t]*[-*•]\s+", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^[ \t]*\d+[.)]\s+", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"[*_]{1,3}")
_BLANK_LINES_RE = re.compile(r"\n\s*\n")
_NEWLINE_RE = re.compile(r"\s*\n+\s*")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def to_speech_text(text: str) -> str:
    text = _MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = _BARE_URL_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _NUMBERED_RE.sub("", text)
    text = _EMPHASIS_RE.sub("", text)
    text = _BLANK_LINES_RE.sub(". ", text)
    text = _NEWLINE_RE.sub(". ", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()
