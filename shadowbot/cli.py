"""
ShadowBot CLI — Main entry point
Terminal REPL dengan Rich UI, slash commands, streaming output
"""
import asyncio
import json
import sys
import os
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

console = Console()

BANNER = """[bold cyan]
  ███████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗██████╗  ██████╗ ████████╗
  ██╔════╝██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║    ██║██╔══██╗██╔═══██╗╚══██╔══╝
  ███████╗███████║███████║██║  ██║██║   ██║██║ █╗ ██║██████╔╝██║   ██║   ██║   
  ╚════██║██╔══██║██╔══██║██║  ██║██║   ██║██║███╗██║██╔══██╗██║   ██║   ██║   
  ███████║██║  ██║██║  ██║██████╔╝╚██████╔╝╚███╔███╔╝██████╔╝╚██████╔╝   ██║   
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═════╝  ╚═════╝   ╚═╝   
[/bold cyan]"""

HELP_TEXT = """
[bold]Slash Commands:[/bold]
  [cyan]/help[/cyan]             Show this help
  [cyan]/provider[/cyan]        Switch AI provider (anthropic/openai/ollama/etc)
  [cyan]/model[/cyan]           Switch model
  [cyan]/clear[/cyan]           Clear conversation history
  [cyan]/memory[/cyan]          Show recent memories
  [cyan]/knowledge[/cyan]       Knowledge base commands (/knowledge add, list, search)
  [cyan]/config[/cyan]          Show current config
  [cyan]/stats[/cyan]           Show agent stats
  [cyan]/exit[/cyan]            Exit ShadowBot

[bold]Examples:[/bold]
  [dim]> search for Python tutorials on YouTube[/dim]
  [dim]> write a Python script to rename files in ~/Downloads[/dim]
  [dim]> what's in my current directory?[/dim]
  [dim]> /knowledge add notes.txt[/dim]
  [dim]> /provider ollama[/dim]
"""


async def run_repl(config: dict):
    """Main REPL loop"""
    from shadowbot.providers import get_provider
    from shadowbot.tools import build_tools
    from shadowbot.memory import MemoryDB
    from shadowbot.rag import RAGEngine
    from shadowbot.agent.loop import AgentLoop

    # Setup dirs
    workspace = Path(config.get("workspace_dir", "~/.shadowbot/workspace")).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    # Init components
    memory = MemoryDB() if config.get("memory_enabled", True) else None
    rag = RAGEngine() if config.get("rag_enabled", True) else None
    tools = build_tools(config, rag_engine=rag, memory=memory)
    provider = get_provider(config)
    agent = AgentLoop(provider=provider, tools=tools, memory=memory, config=config)

    # Prompt session with history
    history_file = Path("~/.shadowbot/history").expanduser()
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        style=Style.from_dict({"prompt": "cyan bold"}),
    )

    console.print(BANNER)
    console.print(Panel(
        f"[cyan]Provider:[/cyan] {provider.name}  "
        f"[cyan]Model:[/cyan] {provider.model}  "
        f"[cyan]Tools:[/cyan] {', '.join(tools.keys())}",
        title="[bold]ShadowBot v1.0[/bold]",
        border_style="cyan",
    ))
    console.print("[dim]Type /help for commands. Ctrl+C or /exit to quit.[/dim]\n")

    while True:
        try:
            user_input = await session.prompt_async("shadow> ")
            user_input = user_input.strip()

            if not user_input:
                continue

            # ── Slash commands ──────────────────────────────────
            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=2)
                cmd = parts[0].lower() if parts else ""

                if cmd in ("exit", "quit", "q"):
                    console.print("[dim]Goodbye.[/dim]")
                    break

                elif cmd == "help":
                    console.print(Panel(HELP_TEXT, title="Help", border_style="cyan"))

                elif cmd == "clear":
                    agent.reset_conversation()
                    console.print("[green]✓[/green] Conversation cleared.")

                elif cmd == "config":
                    _show_config(config)

                elif cmd == "stats":
                    stats = agent.get_stats()
                    _show_stats(stats, tools)

                elif cmd == "provider":
                    if len(parts) < 2:
                        console.print(f"Current: [cyan]{provider.name}[/cyan]")
                        console.print(f"Available: {', '.join(config['providers'].keys())}")
                    else:
                        new_prov = parts[1].lower()
                        if new_prov not in config["providers"]:
                            console.print(f"[red]Unknown provider:[/red] {new_prov}")
                        else:
                            config["provider"] = new_prov
                            provider = get_provider(config)
                            agent.provider = provider
                            console.print(f"[green]✓[/green] Switched to [cyan]{new_prov}[/cyan] / {provider.model}")

                elif cmd == "model":
                    if len(parts) < 2:
                        console.print(f"Current: [cyan]{provider.model}[/cyan]")
                    else:
                        new_model = parts[1]
                        pname = config["provider"]
                        config["providers"][pname]["model"] = new_model
                        provider = get_provider(config)
                        agent.provider = provider
                        console.print(f"[green]✓[/green] Switched to model [cyan]{new_model}[/cyan]")

                elif cmd == "memory":
                    if memory is None:
                        console.print("[yellow]Memory is disabled.[/yellow]")
                    else:
                        _show_memory(memory)

                elif cmd == "knowledge":
                    if rag is None:
                        console.print("[yellow]Knowledge base is disabled.[/yellow]")
                    else:
                        sub = parts[1].lower() if len(parts) > 1 else "list"
                        if sub == "list":
                            _show_knowledge(rag)
                        elif sub == "add" and len(parts) > 2:
                            result = rag.add_file(parts[2])
                            console.print(f"[green]{result}[/green]")
                        elif sub == "search" and len(parts) > 2:
                            results = rag.search(parts[2], top_k=3)
                            if results:
                                for r in results:
                                    console.print(Panel(
                                        r["content"][:400],
                                        title=f"[cyan]{r['title']}[/cyan] (score: {r['score']:.2f})",
                                        border_style="dim",
                                    ))
                            else:
                                console.print("[yellow]No results found.[/yellow]")
                        elif sub == "delete" and len(parts) > 2:
                            result = rag.delete_source(parts[2])
                            console.print(f"[green]{result}[/green]")
                        elif sub == "stats":
                            stats = rag.stats()
                            console.print(f"Total chunks: [cyan]{stats['total_chunks']}[/cyan]  Sources: [cyan]{stats['total_sources']}[/cyan]")
                        else:
                            console.print(
                                "[dim]Usage: /knowledge [list|add <file>|search <query>|delete <source>|stats][/dim]"
                            )
                else:
                    console.print(f"[yellow]Unknown command:[/yellow] /{cmd}. Type /help for commands.")

                continue

            # ── Agent turn ──────────────────────────────────────
            console.print()

            response_text = ""
            tool_indicator_shown = False

            with Live("", console=console, refresh_per_second=15) as live:
                display_buf = ""
                async for chunk in agent.run_turn_stream(user_input):
                    if chunk.startswith("[tool:") or chunk.startswith("[/tool:"):
                        # Show tool activity outside Live
                        pass
                    else:
                        display_buf += chunk
                        response_text = display_buf
                        # Render as markdown in Live
                        live.update(Markdown(display_buf))

            if not response_text.strip():
                # Fallback: non-streaming turn
                response_text = await agent.run_turn(user_input)
                console.print(Markdown(response_text))

            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]Use /exit to quit.[/dim]")
        except EOFError:
            console.print("\n[dim]Goodbye.[/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            if os.environ.get("SHADOWBOT_DEBUG"):
                import traceback
                traceback.print_exc()


def _show_config(config: dict):
    t = Table(title="Config", border_style="cyan", show_header=False)
    t.add_column("Key", style="cyan")
    t.add_column("Value", style="white")

    pname = config.get("provider", "anthropic")
    prov = config.get("providers", {}).get(pname, {})
    t.add_row("Active Provider", pname)
    t.add_row("Active Model", prov.get("model") or config.get("model", ""))
    t.add_row("Memory", "✓" if config.get("memory_enabled") else "✗")
    t.add_row("RAG", "✓" if config.get("rag_enabled") else "✗")
    t.add_row("Web Search", "✓" if config.get("web_search_enabled") else "✗")
    t.add_row("Bash", "✓" if config.get("bash_enabled") else "✗")
    t.add_row("Workspace", config.get("workspace_dir", "~/.shadowbot/workspace"))
    console.print(t)


def _show_stats(stats: dict, tools: dict):
    t = Table(title="Agent Stats", border_style="cyan", show_header=False)
    t.add_column("Key", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("Provider", stats["provider"])
    t.add_row("Model", stats["model"])
    t.add_row("Turns", str(stats["turns"]))
    t.add_row("Messages", str(stats["messages"]))
    t.add_row("Tools loaded", str(len(tools)))
    console.print(t)


def _show_memory(memory):
    items = memory.get_all(limit=10)
    if not items:
        console.print("[dim]No memories stored yet.[/dim]")
        return
    t = Table(title="Recent Memories", border_style="cyan")
    t.add_column("Date", style="dim", width=20)
    t.add_column("Summary", style="white")
    for item in items:
        t.add_row(item["date"][:19], item["summary"][:80] or item["user"][:80])
    console.print(t)


def _show_knowledge(rag):
    sources = rag.list_sources()
    if not sources:
        console.print("[dim]Knowledge base is empty. Use /knowledge add <file> to add documents.[/dim]")
        return
    t = Table(title="Knowledge Base", border_style="cyan")
    t.add_column("Source", style="cyan")
    t.add_column("Chunks", style="white", justify="right")
    t.add_column("Added", style="dim")
    for s in sources:
        name = Path(s["source"]).name if "/" in s["source"] else s["source"]
        t.add_row(name, str(s["chunks"]), s["added"][:10])
    stats = rag.stats()
    console.print(t)
    console.print(f"[dim]Total: {stats['total_chunks']} chunks from {stats['total_sources']} sources[/dim]")


# ─────────────────────────────────────────────
# CLI Entry Points
# ─────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """ShadowBot — Unified AI Agent (nanobot + NOMAD + OpenClaude)"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(agent_cmd)


@cli.command("agent")
@click.option("--provider", "-p", default=None, help="Provider to use")
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--message", default=None, help="Single message (non-interactive)")
@click.option("--config", "config_path", default=None, help="Config file path")
def agent_cmd(provider, model, message, config_path):
    """Start the agent REPL"""
    from shadowbot.config import load_config, validate_config, save_config, CONFIG_PATH

    config = load_config(config_path)

    # CLI overrides
    if provider:
        config["provider"] = provider
    if model:
        pname = config["provider"]
        if pname not in config["providers"]:
            config["providers"][pname] = {}
        config["providers"][pname]["model"] = model

    # Validate
    valid, msg = validate_config(config)
    if not valid:
        console.print(f"[red]Config error:[/red] {msg}")
        console.print(f"[dim]Run: shadowbot setup  — to configure[/dim]")
        sys.exit(1)

    if message:
        # Non-interactive single turn
        async def _single():
            from shadowbot.providers import get_provider
            from shadowbot.tools import build_tools
            from shadowbot.memory import MemoryDB
            from shadowbot.rag import RAGEngine
            from shadowbot.agent.loop import AgentLoop

            memory = MemoryDB() if config.get("memory_enabled") else None
            rag = RAGEngine() if config.get("rag_enabled") else None
            tools = build_tools(config, rag_engine=rag, memory=memory)
            prov = get_provider(config)
            agent = AgentLoop(provider=prov, tools=tools, memory=memory, config=config)
            result = await agent.run_turn(message)
            console.print(Markdown(result))

        asyncio.run(_single())
    else:
        asyncio.run(run_repl(config))


@cli.command("setup")
@click.option("--config", "config_path", default=None)
def setup_cmd(config_path):
    """Interactive setup wizard"""
    from shadowbot.config import load_config, save_config, CONFIG_PATH

    console.print(Panel("[bold cyan]ShadowBot Setup Wizard[/bold cyan]", border_style="cyan"))

    config = load_config(config_path)

    # Provider selection
    providers = list(config["providers"].keys())
    console.print("\n[cyan]Available providers:[/cyan]")
    for i, p in enumerate(providers, 1):
        console.print(f"  {i}. {p}")

    current = config.get("provider", "anthropic")
    choice = console.input(f"\nProvider ([dim]{current}[/dim]): ").strip()
    if choice and choice in providers:
        config["provider"] = choice
    elif choice.isdigit() and 1 <= int(choice) <= len(providers):
        config["provider"] = providers[int(choice) - 1]

    pname = config["provider"]
    prov_cfg = config["providers"][pname]

    # API key (skip for ollama)
    if pname != "ollama":
        current_key = prov_cfg.get("api_key", "")
        masked = f"{current_key[:8]}..." if len(current_key) > 8 else "(not set)"
        new_key = console.input(f"API key for {pname} ([dim]{masked}[/dim]): ").strip()
        if new_key:
            prov_cfg["api_key"] = new_key
    else:
        base_url = prov_cfg.get("base_url", "http://localhost:11434/v1")
        new_url = console.input(f"Ollama URL ([dim]{base_url}[/dim]): ").strip()
        if new_url:
            prov_cfg["base_url"] = new_url

    # Model
    current_model = prov_cfg.get("model", "")
    new_model = console.input(f"Model ([dim]{current_model}[/dim]): ").strip()
    if new_model:
        prov_cfg["model"] = new_model

    # Features
    for feature in ["memory_enabled", "rag_enabled", "web_search_enabled", "bash_enabled"]:
        curr = config.get(feature, True)
        label = feature.replace("_enabled", "").replace("_", " ").title()
        ans = console.input(f"Enable {label}? ([dim]{'y' if curr else 'n'}[/dim]) [y/n]: ").strip().lower()
        if ans in ("y", "n"):
            config[feature] = ans == "y"

    save_path = Path(config_path).expanduser() if config_path else CONFIG_PATH
    save_config(config, str(save_path))
    console.print(f"\n[green]✓[/green] Config saved to [cyan]{save_path}[/cyan]")
    console.print("[dim]Run 'shadowbot' to start.[/dim]")


@cli.command("version")
def version_cmd():
    """Show version"""
    console.print("[cyan]ShadowBot[/cyan] v1.0.0")
    console.print("[dim]Unified AI Agent — nanobot + NOMAD + OpenClaude[/dim]")


def main():
    cli()


if __name__ == "__main__":
    main()
