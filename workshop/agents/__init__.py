from .base import AgentAdapter, AgentProcess, AgentUnavailable, LaunchSpec
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .fake import FakeAdapter


def make_adapters(settings, fake: bool = False, fake_delay: float = 1.5, behavior: str = "demo") -> dict[str, AgentAdapter]:
    """Real CLI adapters, or fake agents (which play the scripted demo scenario by default)."""
    if fake:
        return {a: FakeAdapter(a, fake_delay, behavior=behavior) for a in ("Codex", "Claude")}
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
