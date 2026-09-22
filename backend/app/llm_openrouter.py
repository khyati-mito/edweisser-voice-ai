import json
import logging
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from .llm_common import (
    ChatReply,
    SENTENCE_SPLIT_RE,
    build_system_prompt,
    execute_client_tool,
    get_lock,
    to_openai_tools,
)

logger = logging.getLogger("voice_ai.llm_openrouter")

_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={"X-Title": "Edweisser"},
)

MAX_TOOL_ITERATIONS = 5
TOOLS = to_openai_tools()

# In-memory per-session conversation history, in OpenAI message format
# (separate from llm_anthropic's, since the shapes aren't compatible).
_sessions: dict[str, list[dict]] = {}


async def get_reply(
    session_id: str,
    user_text: str,
    on_sentence: Callable[[str], Awaitable[None]] | None = None,
) -> ChatReply:
    """Same contract as llm_anthropic.get_reply -- see its docstring. The
    system prompt is sent fresh as a leading message on every call (not
    stored in history) so its date/time stays current, matching how the
    Anthropic path handles its separate `system` parameter."""
    async with get_lock(session_id):
        history = _sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": user_text})

        demo_actions: list[dict] = []
        raw_text_parts: list[str] = []
        buffer = ""

        async def emit(sentence: str):
            sentence = sentence.strip()
            if sentence and on_sentence:
                await on_sentence(sentence)

        for _ in range(MAX_TOOL_ITERATIONS):
            messages_for_api = [{"role": "system", "content": build_system_prompt()}] + history
            stream = await _client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages_for_api,
                tools=TOOLS,
                max_tokens=800,
                stream=True,
            )

            content_parts: list[str] = []
            # Tool call fragments arrive spread across multiple chunks,
            # keyed by index -- function.arguments in particular streams as
            # partial JSON string pieces that must be concatenated before
            # they can be json.loads()ed once the call is complete.
            tool_calls_acc: dict[int, dict] = {}
            finish_reason = None

            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    content_parts.append(delta.content)
                    raw_text_parts.append(delta.content)
                    buffer += delta.content
                    parts = SENTENCE_SPLIT_RE.split(buffer)
                    if len(parts) > 1:
                        for sentence in parts[:-1]:
                            await emit(sentence)
                        buffer = parts[-1]
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        slot = tool_calls_acc.setdefault(tc.index, {"id": None, "name": None, "arguments": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            assistant_message: dict = {"role": "assistant", "content": "".join(content_parts) or None}
            if tool_calls_acc:
                assistant_message["tool_calls"] = [
                    {
                        "id": slot["id"],
                        "type": "function",
                        "function": {"name": slot["name"], "arguments": slot["arguments"]},
                    }
                    for slot in tool_calls_acc.values()
                ]
            history.append(assistant_message)

            if finish_reason == "tool_calls" and tool_calls_acc:
                for slot in tool_calls_acc.values():
                    try:
                        args = json.loads(slot["arguments"]) if slot["arguments"] else {}
                    except json.JSONDecodeError as exc:
                        logger.warning("Bad tool call arguments from model: %r (%s)", slot["arguments"], exc)
                        args = {}
                    result = await execute_client_tool(slot["name"], args)
                    if result.get("status") == "simulated":
                        demo_actions.append({"tool": slot["name"], "note": result.get("note", "")})
                    history.append(
                        {"role": "tool", "tool_call_id": slot["id"], "content": json.dumps(result)}
                    )
                continue

            break

        if buffer.strip():
            await emit(buffer)

        reply_text = "".join(raw_text_parts).strip()
        if not reply_text:
            reply_text = "Sorry, let me gather my thoughts on that -- could you say that again?"
            if on_sentence:
                await on_sentence(reply_text)

        return ChatReply(text=reply_text, demo_actions=demo_actions)
