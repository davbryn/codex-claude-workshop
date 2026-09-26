from .base import AgentAdapter, AgentProcess, AgentUnavailable, LaunchSpec
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .fake import FakeAdapter


def make_adapters(settings, fake: bool = False, fake_delay: float = 1.5) -> dict[str, AgentAdapter]:
    if fake:
        return {"Codex": FakeAdapter("Codex", fake_delay), "Claude": FakeAdapter("Claude", fake_delay)}
    return {
        "Codex": CodexAdapter(settings.codex_command, settings.codex_args),
        "Claude": ClaudeAdapter(settings.claude_command, settings.claude_args),
    }


__all__ = [
    "AgentAdapter",
    "AgentProcess",
    "AgentUnavailable",
    "LaunchSpec",
    "ClaudeAdapter",
    "CodexAdapter",
    "FakeAdapter",
    "make_adapters",
]
