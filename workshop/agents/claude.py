"""Claude Code CLI adapter.

Verified against ``claude 2.1.282``::

    claude -p --output-format stream-json --verbose [OPTIONS]   # prompt on stdin

stream-json emits one JSON event per line, which we condense into readable
lines for the output panel so the human can see tool calls live.
"""

from __future__ import annotations

import json
import re
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
            lines = []
            for block in event.get("message", {}).get("content", []):
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                if block.get("is_error"):
                    lines.append(f"[tool error] {_summarise(block.get('content'))}")
                    continue
                # Surface only test-summary lines (e.g. "12 passed in 0.3s") so the
                # output panel stays readable while the UI can react to results.
                for text_line in _content_text(block.get("content")).splitlines():
                    if _TEST_SUMMARY.search(text_line):
                        lines.append(f"[tool result] {text_line.strip()[:200]}")
            return "\n".join(lines) or None
        if kind == "result":
            cost = event.get("total_cost_usd")
            cost_text = f", cost ${cost:.4f}" if isinstance(cost, (int, float)) else ""
            summary = (
                f"[result] {event.get('subtype', '')} after {event.get('num_turns', '?')} steps"
                f"{cost_text}, {event.get('duration_ms', 0) / 1000:.0f}s"
            )
            if event.get("is_error") and event.get("result"):
                summary += f"\n[result error] {str(event['result'])[:300]}"
            return summary
        if kind == "rate_limit_event":
            # Only a rejection matters (the CLI also reports "allowed" status as it goes).
            info = event.get("rate_limit_info") or {}
            if info.get("status") == "rejected":
                reset = info.get("resetsAt")
                window = info.get("rateLimitType", "usage")
                return f"[usage limit] {window} limit reached" + (f"|{int(reset)}" if reset else "")
            return None
        return None


_TEST_SUMMARY = re.compile(
    r"\b\d+ passed\b.*\bin [\d.]+s|^Ran \d+ tests? in|^OK(?: \(|$)|^FAILED \(|^Tests:\s+.*\d+ passed|"
    r"test result: (?:ok|FAILED)\.|\bALL (?:TESTS )?PASSED\b|\b\d+ failed\b",
    re.I,
)


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
    return ""


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
