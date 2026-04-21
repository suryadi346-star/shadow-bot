"""
ShadowBot Agent Loop
Core agent engine inspired by nanobot (HKUDS)
Handles: LLM calls, tool dispatch, streaming, memory, conversation history
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Optional, Any
from pathlib import Path
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.panel import Panel

console = Console()


class AgentLoop:
    """
    Main agent loop — Perceive → Think → Act → Observe
    Inspired by nanobot's minimal loop design
    """

    def __init__(self, provider, tools: dict, memory, config: dict):
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.config = config
        self.conversation: list[dict] = []
        self.running = False
        self.current_task: Optional[str] = None
        self.max_iterations = config.get("max_iterations", 20)

    def add_message(self, role: str, content: str):
        self.conversation.append({"role": role, "content": content})
        # Keep last N turns to manage context window
        max_history = self.config.get("max_history", 50)
        if len(self.conversation) > max_history:
            self.conversation = self.conversation[-max_history:]

    def get_system_prompt(self) -> str:
        base = self.config.get("system_prompt", "")
        memory_context = self.memory.get_context() if self.memory else ""
        if memory_context:
            base += f"\n\n## Memory Context\n{memory_context}"
        return base

    def build_tools_schema(self) -> list[dict]:
        """Build tool definitions for LLM"""
        return [tool.schema for tool in self.tools.values()]

    async def run_turn(self, user_input: str) -> str:
        """Run one full agent turn with tool use loop"""
        self.add_message("user", user_input)
        self.current_task = user_input

        iteration = 0
        full_response = ""

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM
            messages = self.conversation.copy()
            system = self.get_system_prompt()
            tools_schema = self.build_tools_schema()

            response_text, tool_calls = await self.provider.chat(
                messages=messages,
                system=system,
                tools=tools_schema,
            )

            if response_text:
                full_response = response_text

            # No tool calls = final answer
            if not tool_calls:
                if response_text:
                    self.add_message("assistant", response_text)
                    # Save to memory
                    if self.memory:
                        await self.memory.save_turn(user_input, response_text)
                break

            # Execute tool calls
            tool_results = []
            for tool_call in tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", f"call_{iteration}")

                console.print(
                    f"[dim cyan]▶ Tool:[/dim cyan] [cyan]{tool_name}[/cyan] "
                    f"[dim]{json.dumps(tool_args)[:80]}[/dim]"
                )

                result = await self._execute_tool(tool_name, tool_args)

                console.print(
                    f"[dim green]◀ Result:[/dim green] [dim]{str(result)[:120]}[/dim]"
                )

                tool_results.append({
                    "id": tool_id,
                    "name": tool_name,
                    "result": str(result),
                })

            # Add assistant + tool results to conversation
            self.add_message("assistant", json.dumps({
                "text": response_text or "",
                "tool_calls": tool_calls,
            }))
            self.add_message("tool", json.dumps(tool_results))

        return full_response or "I encountered an issue. Please try again."

    async def run_turn_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """Streaming version of run_turn"""
        self.add_message("user", user_input)
        self.current_task = user_input

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            messages = self.conversation.copy()
            system = self.get_system_prompt()
            tools_schema = self.build_tools_schema()

            full_text = ""
            tool_calls = []

            # Stream the response
            async for chunk in self.provider.chat_stream(
                messages=messages,
                system=system,
                tools=tools_schema,
            ):
                if chunk.get("type") == "text":
                    text = chunk.get("content", "")
                    full_text += text
                    yield text
                elif chunk.get("type") == "tool_call":
                    tool_calls.append(chunk.get("content"))
                elif chunk.get("type") == "done":
                    break

            if not tool_calls:
                if full_text:
                    self.add_message("assistant", full_text)
                    if self.memory:
                        await self.memory.save_turn(user_input, full_text)
                break

            # Execute tools (non-streaming for simplicity)
            tool_results = []
            for tool_call in tool_calls:
                if not tool_call:
                    continue
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", f"call_{iteration}")

                yield f"\n[tool:{tool_name}]"
                result = await self._execute_tool(tool_name, tool_args)
                yield f"[/tool:{result[:100]}]\n"

                tool_results.append({
                    "id": tool_id,
                    "name": tool_name,
                    "result": str(result),
                })

            self.add_message("assistant", json.dumps({
                "text": full_text,
                "tool_calls": tool_calls,
            }))
            self.add_message("tool", json.dumps(tool_results))

    async def _execute_tool(self, name: str, args: dict) -> Any:
        """Execute a registered tool"""
        if name not in self.tools:
            return f"Error: tool '{name}' not found. Available: {list(self.tools.keys())}"
        try:
            tool = self.tools[name]
            if asyncio.iscoroutinefunction(tool.run):
                return await tool.run(**args)
            return tool.run(**args)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

    def reset_conversation(self):
        """Clear conversation history"""
        self.conversation = []
        self.current_task = None

    def get_stats(self) -> dict:
        return {
            "turns": len([m for m in self.conversation if m["role"] == "user"]),
            "messages": len(self.conversation),
            "provider": self.provider.name,
            "model": self.provider.model,
        }
