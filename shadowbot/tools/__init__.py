"""
ShadowBot Tools
Inspired by: nanobot tools + OpenClaude bash/file tools + NOMAD knowledge tools
Semua tools Termux-safe (no subprocess sandboxing yang perlu bwrap)
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any


class BaseTool:
    name: str = ""
    description: str = ""
    schema: dict = {}

    async def run(self, **kwargs) -> Any:
        raise NotImplementedError


# ─────────────────────────────────────────────
# WEB SEARCH TOOL
# ─────────────────────────────────────────────
class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information. Use for news, facts, documentation, anything that requires up-to-date data."
    schema = {
        "name": "web_search",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                }
            },
            "required": ["query"],
        },
    }

    async def run(self, query: str) -> str:
        try:
            # Try ddgs first (new package name)
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if not results:
                return f"No results found for: {query}"

            output = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                output.append(f"{i}. **{title}**\n{body}\n{href}")

            return "\n\n".join(output)
        except Exception as e:
            return f"Search error: {str(e)}"


# ─────────────────────────────────────────────
# BASH / SHELL TOOL
# ─────────────────────────────────────────────
class BashTool(BaseTool):
    name = "run_bash"
    description = "Execute a shell command and return its output. Use for file operations, running scripts, system info, git commands, etc."
    schema = {
        "name": "run_bash",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
    }

    def __init__(self, workspace_dir: str = None, allowed: bool = True):
        self.workspace_dir = Path(workspace_dir).expanduser() if workspace_dir else Path.home()
        self.allowed = allowed
        # Dangerous commands blocklist
        self._blocklist = ["rm -rf /", "mkfs", ":(){:|:&};:", "dd if=/dev/zero"]

    async def run(self, command: str, timeout: int = 30) -> str:
        if not self.allowed:
            return "Error: bash execution is disabled. Enable it in config."

        # Basic safety check
        for blocked in self._blocklist:
            if blocked in command:
                return f"Error: command blocked for safety: '{blocked}'"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.workspace_dir),
                env={**os.environ},
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return f"Error: command timed out after {timeout}s"

            output = stdout.decode("utf-8", errors="replace")
            # Truncate long output
            if len(output) > 8000:
                output = output[:4000] + "\n...[truncated]...\n" + output[-2000:]
            return output or "(no output)"
        except Exception as e:
            return f"Error: {str(e)}"


# ─────────────────────────────────────────────
# FILE READ TOOL
# ─────────────────────────────────────────────
class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Returns the file content as text."
    schema = {
        "name": "read_file",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Max lines to return (default: 200)",
                    "default": 200,
                },
            },
            "required": ["path"],
        },
    }

    async def run(self, path: str, max_lines: int = 200) -> str:
        try:
            p = Path(path).expanduser()
            if not p.exists():
                return f"Error: file not found: {path}"
            if not p.is_file():
                return f"Error: not a file: {path}"
            if p.stat().st_size > 5 * 1024 * 1024:
                return f"Error: file too large (>5MB): {path}"

            content = p.read_text(errors="replace")
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines]) + f"\n...[{len(lines) - max_lines} more lines]"
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"


# ─────────────────────────────────────────────
# FILE WRITE TOOL
# ─────────────────────────────────────────────
class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Creates the file and parent directories if they don't exist."
    schema = {
        "name": "write_file",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append instead of overwrite",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        },
    }

    async def run(self, path: str, content: str, append: bool = False) -> str:
        try:
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode, encoding="utf-8") as f:
                f.write(content)
            action = "appended" if append else "written"
            return f"✓ {action} {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


# ─────────────────────────────────────────────
# LIST DIRECTORY TOOL
# ─────────────────────────────────────────────
class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and directories in a path."
    schema = {
        "name": "list_dir",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list",
                    "default": ".",
                },
            },
            "required": [],
        },
    }

    async def run(self, path: str = ".") -> str:
        try:
            p = Path(path).expanduser()
            if not p.exists():
                return f"Error: path not found: {path}"
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = []
            for item in items[:100]:
                icon = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    size = f" ({s:,} bytes)"
                lines.append(f"{icon} {item.name}{size}")
            if not lines:
                return "(empty directory)"
            result = "\n".join(lines)
            if len(items) > 100:
                result += f"\n... and {len(items) - 100} more"
            return result
        except Exception as e:
            return f"Error: {str(e)}"


# ─────────────────────────────────────────────
# KNOWLEDGE BASE SEARCH TOOL (NOMAD-inspired RAG)
# ─────────────────────────────────────────────
class KnowledgeSearchTool(BaseTool):
    name = "search_knowledge"
    description = "Search the local knowledge base for stored documents, notes, and uploaded files. Use this before web search for topics you might have saved locally."
    schema = {
        "name": "search_knowledge",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    }

    def __init__(self, rag_engine):
        self.rag = rag_engine

    async def run(self, query: str, top_k: int = 3) -> str:
        if self.rag is None:
            return "Knowledge base not initialized."
        results = self.rag.search(query, top_k=top_k)
        if not results:
            return "No matching documents found in knowledge base."
        output = []
        for i, r in enumerate(results, 1):
            output.append(f"{i}. [{r['source']}]\n{r['content'][:500]}")
        return "\n\n".join(output)


# ─────────────────────────────────────────────
# MEMORY RECALL TOOL
# ─────────────────────────────────────────────
class MemoryRecallTool(BaseTool):
    name = "recall_memory"
    description = "Search past conversation memory for relevant context from previous sessions."
    schema = {
        "name": "recall_memory",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to recall",
                },
            },
            "required": ["query"],
        },
    }

    def __init__(self, memory):
        self.memory = memory

    async def run(self, query: str) -> str:
        if self.memory is None:
            return "Memory not initialized."
        results = self.memory.search(query, top_k=3)
        if not results:
            return "No relevant memories found."
        return "\n\n".join([f"[{r['date']}] {r['content']}" for r in results])


# ─────────────────────────────────────────────
# TOOL REGISTRY BUILDER
# ─────────────────────────────────────────────
def build_tools(config: dict, rag_engine=None, memory=None) -> dict:
    """Build tool registry based on config"""
    tools = {}

    if config.get("web_search_enabled", True):
        tools["web_search"] = WebSearchTool()

    if config.get("bash_enabled", True):
        workspace = config.get("workspace_dir", "~/.shadowbot/workspace")
        tools["run_bash"] = BashTool(workspace_dir=workspace)

    tools["read_file"] = ReadFileTool()
    tools["write_file"] = WriteFileTool()
    tools["list_dir"] = ListDirTool()

    if rag_engine and config.get("rag_enabled", True):
        tools["search_knowledge"] = KnowledgeSearchTool(rag_engine)

    if memory and config.get("memory_enabled", True):
        tools["recall_memory"] = MemoryRecallTool(memory)

    return tools
