"""
OpenAI-compatible provider
Covers: OpenAI, Ollama, OpenRouter, DeepSeek, Gemini, LM Studio, dan semua
provider dengan OpenAI-compatible API.
Inspired by OpenClaude's multi-provider routing.
"""
import json
from typing import AsyncGenerator, Optional
from .base import BaseProvider

# Default base URLs per provider name
PROVIDER_DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "lmstudio": "http://localhost:1234/v1",
}


class OpenAIProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        provider_name: str = "openai",
    ):
        import openai
        self.name = provider_name
        self.model = model

        resolved_url = base_url or PROVIDER_DEFAULTS.get(provider_name)
        resolved_key = api_key or "ollama"  # ollama tidak butuh key

        self.client = openai.AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_url,
        )

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert ShadowBot schema → OpenAI function calling format"""
        if not tools:
            return []
        converted = []
        for t in tools:
            converted.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {
                        "type": "object",
                        "properties": {},
                    }),
                },
            })
        return converted

    def _convert_messages(self, messages: list[dict], system: str) -> list[dict]:
        """Build final messages list with system prompt"""
        result = []
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "tool":
                # Tool results — parse and inject as tool role messages
                try:
                    tool_results = json.loads(content)
                    for tr in tool_results:
                        result.append({
                            "role": "tool",
                            "tool_call_id": tr.get("id", "call_0"),
                            "content": str(tr.get("result", "")),
                        })
                except (json.JSONDecodeError, TypeError):
                    pass
                continue

            if role == "assistant":
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "tool_calls" in parsed:
                        # Assistant message with tool calls
                        tc_list = []
                        for tc in parsed.get("tool_calls", []):
                            tc_list.append({
                                "id": tc.get("id", "call_0"),
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc.get("args", {})),
                                },
                            })
                        result.append({
                            "role": "assistant",
                            "content": parsed.get("text") or None,
                            "tool_calls": tc_list,
                        })
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            result.append({"role": role, "content": content})
        return result

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> tuple[str, list[dict]]:
        msgs = self._convert_messages(messages, system)
        kwargs = dict(model=self.model, messages=msgs)
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        text = msg.content or ""
        tool_calls = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                })

        return text, tool_calls

    async def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        msgs = self._convert_messages(messages, system)
        kwargs = dict(model=self.model, messages=msgs, stream=True)
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        tool_calls_buffer: dict[int, dict] = {}

        async with await self.client.chat.completions.create(**kwargs) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Text content
                if delta.content:
                    yield {"type": "text", "content": delta.content}

                # Tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": "",
                                "name": "",
                                "args_str": "",
                            }
                        buf = tool_calls_buffer[idx]
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                buf["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                buf["args_str"] += tc_delta.function.arguments

                finish = chunk.choices[0].finish_reason if chunk.choices else None
                if finish in ("tool_calls", "stop"):
                    for idx, buf in tool_calls_buffer.items():
                        try:
                            args = json.loads(buf["args_str"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        yield {
                            "type": "tool_call",
                            "content": {
                                "id": buf["id"] or f"call_{idx}",
                                "name": buf["name"],
                                "args": args,
                            },
                        }
                    yield {"type": "done", "content": None}
                    return

        yield {"type": "done", "content": None}
