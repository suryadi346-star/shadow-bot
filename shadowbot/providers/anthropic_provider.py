"""Anthropic provider — native SDK dengan tool use dan streaming"""
import json
from typing import AsyncGenerator
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        import anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=api_key)

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert ShadowBot tool schema → Anthropic format"""
        if not tools:
            return []
        converted = []
        for t in tools:
            converted.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Normalize messages — handle tool results stored as JSON strings"""
        converted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Skip internal tool result messages (re-injected differently)
            if role == "tool":
                continue

            # Decode assistant messages that contain tool calls
            if role == "assistant":
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "tool_calls" in parsed:
                        blocks = []
                        if parsed.get("text"):
                            blocks.append({"type": "text", "text": parsed["text"]})
                        for tc in parsed.get("tool_calls", []):
                            blocks.append({
                                "type": "tool_use",
                                "id": tc.get("id", "tool_0"),
                                "name": tc["name"],
                                "input": tc.get("args", {}),
                            })
                        converted.append({"role": "assistant", "content": blocks})
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            converted.append({"role": role, "content": content})
        return converted

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> tuple[str, list[dict]]:
        msgs = self._convert_messages(messages)
        kwargs = dict(
            model=self.model,
            max_tokens=8192,
            messages=msgs,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self.async_client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "args": block.input,
                })

        return "\n".join(text_parts), tool_calls

    async def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        msgs = self._convert_messages(messages)
        kwargs = dict(
            model=self.model,
            max_tokens=8192,
            messages=msgs,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        tool_calls_buffer = {}

        async with self.async_client.messages.stream(**kwargs) as stream:
            async for event in stream:
                etype = type(event).__name__

                if etype == "RawContentBlockDeltaEvent":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        yield {"type": "text", "content": delta.text}
                    elif hasattr(delta, "partial_json"):
                        idx = event.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"json_str": ""}
                        tool_calls_buffer[idx]["json_str"] += delta.partial_json

                elif etype == "RawContentBlockStartEvent":
                    block = event.content_block
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_calls_buffer[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "json_str": "",
                        }

                elif etype == "RawContentBlockStopEvent":
                    idx = event.index
                    if idx in tool_calls_buffer:
                        buf = tool_calls_buffer[idx]
                        if "name" in buf:
                            try:
                                args = json.loads(buf["json_str"] or "{}")
                            except json.JSONDecodeError:
                                args = {}
                            yield {
                                "type": "tool_call",
                                "content": {
                                    "id": buf.get("id", f"call_{idx}"),
                                    "name": buf["name"],
                                    "args": args,
                                },
                            }

                elif etype == "RawMessageStopEvent":
                    yield {"type": "done", "content": None}
