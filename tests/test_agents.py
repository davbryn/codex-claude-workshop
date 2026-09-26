import json
import sys
from pathlib import Path

import pytest

from workshop.agents.base import AgentAdapter
from workshop.agents.claude import ClaudeAdapter
from workshop.agents.codex import CodexAdapter


class ShimAdapter(AgentAdapter):
    name = "Codex"

    def build_launch(self, project_dir, prompt):
        return self.make_spec(self.resolve_executable(), ["exec", "--cd", str(project_dir), "-"], stdin=prompt)


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe shims are Windows-only")
def test_cmd_shim_in_path_with_spaces_runs(qapp, wait, tmp_path):
    shim_dir = tmp_path / "dir with spaces"
    shim_dir.mkdir()
    shim = shim_dir / "fakecli.cmd"
    shim.write_text("@echo off\r\necho ARGS %*\r\nmore\r\nexit /b 0\r\n", encoding="ascii")
    project = tmp_path / "my project"
    project.mkdir()

    adapter = ShimAdapter(str(shim))
    proc = adapter.start_turn(project, "hello from stdin")
    lines, result = [], []
    proc.output.connect(lambda stream, line: lines.append(line))
    proc.finished.connect(lambda code, crashed: result.append((code, crashed)))
    assert wait(lambda: result, timeout=10)
    assert result == [(0, False)], lines
    out = "\n".join(lines)
    assert "ARGS exec --cd" in out and "my project" in out
    assert "hello from stdin" in out


def test_codex_command_line(tmp_path):
    adapter = CodexAdapter(sys.executable)  # any real executable stands in for codex
    spec = adapter.build_launch(tmp_path, "PROMPT")
    assert spec.program == sys.executable
    assert spec.args[0] == "exec" and spec.args[-1] == "-"
    assert "--skip-git-repo-check" in spec.args and str(tmp_path) in spec.args
    assert spec.args[spec.args.index("--sandbox") + 1] == "workspace-write"
    assert spec.stdin == "PROMPT"


def test_claude_command_line_and_env(tmp_path):
    adapter = ClaudeAdapter(sys.executable, ["--model", "x"])
    spec = adapter.build_launch(tmp_path, "PROMPT")
    assert spec.args[:4] == ["-p", "--output-format", "stream-json", "--verbose"]
    assert spec.args[-2:] == ["--model", "x"]
    assert "CLAUDECODE" in spec.remove_env and spec.stdin == "PROMPT"


def test_claude_stream_json_formatting():
    fmt = ClaudeAdapter().format_output_line
    assistant = {
        "type": "assistant",
        "message": {"content": [
            {"type": "text", "text": "Let me look."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
        ]},
    }
    assert fmt(json.dumps(assistant)) == "Let me look.\n[tool] Bash: pytest -q"
    result = {"type": "result", "subtype": "success", "num_turns": 4, "total_cost_usd": 0.1, "duration_ms": 9000}
    assert fmt(json.dumps(result)).startswith("[result] success after 4 steps")
    assert fmt(json.dumps({"type": "user", "message": {"content": []}})) is None
    assert fmt("not json") == "not json"


def test_missing_executable_message():
    with pytest.raises(Exception, match="Claude executable not found"):
        ClaudeAdapter("no-such-claude-binary-xyz").build_launch(Path("."), "p")
