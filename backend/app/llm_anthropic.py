import json
import logging
from collections.abc import Awaitable, Callable

from anthropic import AsyncAnthropic

from .config import ANTHROPIC_API_KEY
from .llm_common import (
    ChatReply,
    SENTENCE_SPLIT_RE,
    build_system_prompt,
    execute_client_tool,
    get_lock,
    to_anthropic_tools,
)

logger = logging.getLogger("voice_ai.llm_anthropic")

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-5"
MAX_TOOL_ITERATIONS = 5
TOOLS = to_anthropic_tools()

# In-memory per-session conversation history, in Anthropic's message format.
# Fine for a single-process POC; swap for a real store if this needs to
# survive restarts or scale out.
_sessions: dict[str, list[dict]] = {}


async def get_reply(
    session_id: str,
    user_text: str,
    on_sentence: Callable[[str], Awaitable[None]] | None = None,
) -> ChatReply:
    """Runs one turn: user_text in, a ChatReply out. If on_sentence is given,
    it's awaited with each complete sentence as soon as Claude streams it --
    across tool-use round trips too, so even a "let me check that" aside
    before a tool call streams out immediately. Without it (the typed /chat
    path), this is just a streamed equivalent of a single blocking call."""
    async with get_lock(session_id):
        history = _sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": user_text})

        demo_actions: list[dict] = []
        # raw_text_parts preserves Claude's original text exactly (including
        # paragraph breaks the typed chat UI relies on) for the returned
        # ChatReply. buffer/emit is a separate, sentence-boundary view of the
        # same text used only to fire on_sentence for streaming -- splitting
        # and rejoining with plain spaces would otherwise flatten every
        # paragraph break into one run-on line.
        raw_text_parts: list[str] = []
        buffer = ""
        final_message = None

        async def emit(sentence: str):
            sentence = sentence.strip()
            if sentence and on_sentence:
                await on_sentence(sentence)

        for _ in range(MAX_TOOL_ITERATIONS):
            async with _client.messages.stream(
                model=MODEL,
                max_tokens=800,
                system=build_system_prompt(),
                messages=history,
                tools=TOOLS,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        raw_text_parts.append(event.delta.text)
                        buffer += event.delta.text
                        parts = SENTENCE_SPLIT_RE.split(buffer)
                        if len(parts) > 1:
                            for sentence in parts[:-1]:
                                await emit(sentence)
                            buffer = parts[-1]
                final_message = await stream.get_final_message()

            # Streaming responses' text blocks come back from model_dump()
            # with an extra "parsed_output": null field (tied to structured
            # outputs) that the API's input schema rejects if echoed back
            # verbatim on the next call ("Extra inputs are not permitted") --
            # confirmed by hitting exactly that 400 in the tool-use loop.
            assistant_content = final_message.model_dump()["content"]
            for block in assistant_content:
                block.pop("parsed_output", None)
            history.append({"role": "assistant", "content": assistant_content})

            if final_message.stop_reason == "tool_use":
                tool_results = []
                for block in final_message.content:
                    if block.type != "tool_use":
                        continue
                    result = await execute_client_tool(block.name, block.input)
                    if result.get("status") == "simulated":
                        demo_actions.append({"tool": block.name, "note": result.get("note", "")})
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                    )
                if not tool_results:
                    break
                history.append({"role": "user", "content": tool_results})
                continue

            if final_message.stop_reason == "pause_turn":
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
