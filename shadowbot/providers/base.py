"""Base provider interface — semua provider harus implement ini"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> tuple[str, list[dict]]:
        """
        Single-turn chat.
        Returns: (response_text, tool_calls)
        tool_calls = [{"id": ..., "name": ..., "args": {...}}]
        """

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming chat.
        Yields dicts: {"type": "text"|"tool_call"|"done", "content": ...}
        """
