"""Pretty-print a LangGraph Studio thread's state in the terminal.

Usage:
    api/.venv/bin/python inspect_thread.py <thread-id>
    api/.venv/bin/python inspect_thread.py --latest

Dumps every message in order with role-coded coloring and unpacks each AI
message's `additional_kwargs.tool_calls_json` (the card-grid / list-editor
widget hints Studio refuses to render) as syntax-highlighted JSON.
Finishes with the current `context_store` so you can see exactly what each
module has confirmed so far.

Talks to the local `langgraph dev` server (defaults to http://127.0.0.1:8123,
override with --api-url). When that server isn't running there's no thread
state to dump, so the script bails with a friendly error.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

console = Console()


def fetch(url: str, *, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        console.print(f"[red bold]Cannot reach {url}[/red bold]: {e}")
        console.print("[dim]Is `langgraph dev` running? It boots on port 8123 by default.[/dim]")
        sys.exit(1)


def find_latest_thread(api_url: str) -> str:
    """Return the most recently updated thread's id (across all assistants)."""
    threads = fetch(
        f"{api_url}/threads/search",
        method="POST",
        body={"limit": 1, "sort_by": "updated_at", "sort_order": "desc"},
    )
    if not threads:
        console.print("[red]No threads found on the langgraph dev server.[/red]")
        console.print("[dim]Start a conversation in Studio first, then re-run.[/dim]")
        sys.exit(1)
    return threads[0]["thread_id"]


def message_text(msg: dict) -> str:
    """Normalize message content (str or content-blocks) to a single string."""
    c = msg.get("content", "")
    if isinstance(c, list):
        parts = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return c if isinstance(c, str) else str(c)


_ROLE_STYLE = {
    "human": ("cyan", "[HUMAN]"),
    "ai":    ("green", "[AI]"),
    "system": ("magenta", "[SYSTEM]"),
    "tool":  ("yellow", "[TOOL]"),
}


def render_message(idx: int, msg: dict) -> None:
    role = msg.get("type", "?")
    color, prefix = _ROLE_STYLE.get(role, ("white", f"[{role.upper()}]"))
    text = message_text(msg)
    header = Text(f"{idx:>2}  {prefix} ", style=f"bold {color}")
    header.append(text, style="white")
    console.print(header)

    # Surface widget hints (card_grid, list_editor) that Studio hides.
    ak = msg.get("additional_kwargs") or {}
    tcj = ak.get("tool_calls_json")
    if tcj:
        widget_type = tcj.get("widget_type", "?")
        field_name = tcj.get("field_name", "?")
        title = f"[bold yellow]widget[/bold yellow]  type=[cyan]{widget_type}[/cyan]  field=[cyan]{field_name}[/cyan]"
        console.print(Panel(JSON(json.dumps(tcj)), title=title, border_style="dim yellow", padding=(0, 1)))


def render_context_store(cs: dict) -> None:
    """Pretty-print the context_store with per-module status hints."""
    console.print(Rule("[bold]context_store[/bold]", style="dim"))
    for module_key, label in [
        ("m1_topic", "M1 — Topic"),
        ("m2_literature", "M2 — Literature"),
        ("m3_design", "M3 — Design"),
        ("m4_analysis", "M4 — Analysis"),
        ("m5_writing", "M5 — Writing"),
    ]:
        slice_ = cs.get(module_key)
        if slice_ is None:
            console.print(f"  [dim]{label}: null[/dim]")
            continue
        confirmed = "confirmed_at" in slice_ and slice_["confirmed_at"]
        marker = "[green]✓[/green]" if confirmed else "[yellow]·[/yellow]"
        console.print(f"  {marker} [bold]{label}[/bold]")
        console.print(Panel(JSON(json.dumps(slice_)), border_style="dim", padding=(0, 1)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("thread_id", nargs="?", help="Thread UUID. Omit and pass --latest to auto-pick.")
    parser.add_argument("--latest", action="store_true", help="Inspect the most recently updated thread.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8123", help="langgraph dev base URL.")
    args = parser.parse_args()

    if not args.thread_id and not args.latest:
        parser.error("Pass a thread_id or use --latest.")
    thread_id = args.thread_id or find_latest_thread(args.api_url)

    state = fetch(f"{args.api_url}/threads/{thread_id}/state")
    values = state.get("values") or {}
    messages = values.get("messages") or []
    cs = values.get("context_store") or {}

    console.print(Rule(f"[bold]thread[/bold]  [cyan]{thread_id}[/cyan]", style="bold"))
    console.print(
        f"[dim]current_module=[/dim][bold]{values.get('current_module', '?')}[/bold]   "
        f"[dim]mode=[/dim][bold]{values.get('mode', '?')}[/bold]   "
        f"[dim]messages=[/dim][bold]{len(messages)}[/bold]"
    )
    console.print()

    for i, msg in enumerate(messages):
        render_message(i, msg)
        console.print()

    if cs:
        render_context_store(cs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
