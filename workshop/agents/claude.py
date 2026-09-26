"""Claude Code CLI adapter.

Verified against ``claude 2.1.282``::

    claude -p --output-format stream-json --verbose [OPTIONS]   # prompt on stdin

stream-json emits one JSON event per line, which we condense into readable
lines for the output panel so the human can see tool calls live.
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import AgentAdapter, LaunchSpec

DEFAULT_CLAUDE_ARGS = ["--permission-mode", "acceptEdits", "--allowedTools", "Bash PowerShell"]

# Set when the app itself is launched from inside a Claude Code session;
# the child would otherwise think it is a nested session.
_NESTED_SESSION_VARS = ["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"]


class ClaudeAdapter(AgentAdapter):
    name = "Claude"

    def __init__(self, command: str = "claude", extra_args: list[str] | None = None):
        super().__init__(command, DEFAULT_CLAUDE_ARGS if extra_args is None else extra_args)

    def build_launch(self, project_dir: Path, prompt: str) -> LaunchSpec:
        path = self.resolve_executable()
        args = ["-p", "--output-format", "stream-json", "--verbose", *self.extra_args]
        return self.make_spec(path, args, stdin=prompt, remove_env=_NESTED_SESSION_VARS)

    def format_output_line(self, line: str) -> str | None:
        if not line.strip():
            return None
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return line
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            return f"[session] model={event.get('model', '?')} cwd={event.get('cwd', '?')}"
        if kind == "assistant":
            parts = []
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    parts.append(block["text"].strip())
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool] {block.get('name')}: {_summarise(block.get('input', {}))}")
            return "\n".join(parts) or None
        if kind == "user":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    return f"[tool error] {_summarise(block.get('content'))}"
            return None
        if kind == "result":
            cost = event.get("total_cost_usd")
            cost_text = f", cost ${cost:.4f}" if isinstance(cost, (int, float)) else ""
            return (
                f"[result] {event.get('subtype', '')} after {event.get('num_turns', '?')} steps"
                f"{cost_text}, {event.get('duration_ms', 0) / 1000:.0f}s"
            )
        return None


def _summarise(value, limit: int = 200) -> str:
    if isinstance(value, dict):
        for key in ("command", "file_path", "path", "pattern", "description"):
            if key in value:
                text = str(value[key])
                break
        else:
            text = json.dumps(value)
    elif isinstance(value, list):
        text = " ".join(str(v.get("text", v)) if isinstance(v, dict) else str(v) for v in value)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
