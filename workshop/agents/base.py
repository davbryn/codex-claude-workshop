"""Agent adapter layer.

An adapter knows how to turn "run one turn of agent X in directory D with
prompt P" into a concrete command line. Everything CLI-specific lives in the
adapter subclasses; the orchestrator only sees :class:`AgentProcess`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


@dataclass
class LaunchSpec:
    program: str
    args: list[str]
    stdin: str | None = None  # prompts go via stdin to dodge Windows quoting/length limits
    env: dict[str, str] = field(default_factory=dict)
    remove_env: list[str] = field(default_factory=list)
    native_arguments: str | None = None  # Windows: raw command line passed verbatim (cmd.exe shims)


class AgentUnavailable(Exception):
    pass


class AgentAdapter:
    """Base class: subclasses implement :meth:`build_launch`."""

    environment_note = ""  # facts about this agent's environment, added to its turn prompt

    name: str = "Agent"
    progress_on_stderr = False  # CLI writes normal progress to stderr (don't label it as errors)

    def __init__(self, command: str = "", extra_args: list[str] | None = None):
        self.command = command
        self.extra_args = list(extra_args or [])

    def build_launch(self, project_dir: Path, prompt: str) -> LaunchSpec:
        raise NotImplementedError

    def format_output_line(self, line: str) -> str | None:
        """Turn one raw stdout line into display text (None hides it)."""
        return line

    def prepare_turn(self, project_dir: Path, prompt: str, parent: QObject | None = None) -> "AgentProcess":
        """Create (but don't start) the process, so callers can connect signals first."""
        return AgentProcess(self, self.build_launch(project_dir, prompt), project_dir, parent)

    def start_turn(self, project_dir: Path, prompt: str, parent: QObject | None = None) -> "AgentProcess":
        proc = self.prepare_turn(project_dir, prompt, parent)
        proc.start()
        return proc

    # -- helpers for subclasses ---------------------------------------------

    def resolve_executable(self, fallback_paths: list[str] | None = None) -> str:
        """Find the configured command on PATH (or as a file path).

        A real executable from ``fallback_paths`` is preferred over a
        ``.cmd``/``.bat`` shim, and is used when the command is not found.
        """
        command = self.command.strip().strip('"')
        path = shutil.which(command) if command else None
        if path is None and command and Path(command).is_file():
            path = command
        if path is None or _is_batch(path):
            for candidate in fallback_paths or []:
                candidate = os.path.expandvars(candidate)
                if Path(candidate).is_file() and not (path and _is_batch(candidate)):
                    path = candidate
                    break
        if path is None:
            raise AgentUnavailable(
                f"{self.name} executable not found (command: {command or '<empty>'}). "
                f"Install it or set the {self.name} command in Advanced settings."
            )
        return path

    @staticmethod
    def make_spec(path: str, args: list[str], **kwargs) -> LaunchSpec:
        """Build a LaunchSpec, running ``.cmd``/``.bat`` shims through cmd.exe.

        CreateProcess can't launch batch files directly, and cmd.exe mangles
        quoted paths containing spaces unless the whole line is wrapped for /s.
        """
        if sys.platform == "win32" and _is_batch(path):
            line = subprocess.list2cmdline([path, *args])
            return LaunchSpec(
                program=os.environ.get("COMSPEC", "cmd.exe"), args=[], native_arguments=f'/d /s /c "{line}"', **kwargs
            )
        return LaunchSpec(program=path, args=args, **kwargs)


def _is_batch(path: str) -> bool:
    return path.lower().endswith((".cmd", ".bat"))


class AgentProcess(QObject):
    """One running agent turn, wrapping QProcess so the UI thread never blocks."""

    output = Signal(str, str)  # stream ("stdout"/"stderr"/"system"), text
    finished = Signal(int, bool)  # exit code, crashed/killed

    def __init__(self, adapter: AgentAdapter, spec: LaunchSpec, project_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.adapter = adapter
        self.spec = spec
        self.killed = False
        self._buffers = {"stdout": "", "stderr": ""}
        self._done = False
        self.stderr_tail: list[str] = []

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(project_dir))
        env = QProcessEnvironment.systemEnvironment()
        for key in spec.remove_env:
            env.remove(key)
        for key, value in spec.env.items():
            env.insert(key, value)
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(lambda: self._read("stdout"))
        self.process.readyReadStandardError.connect(lambda: self._read("stderr"))
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

    def start(self) -> None:
        if self.spec.native_arguments is not None:
            self.output.emit("system", f"$ {self.spec.program} {self.spec.native_arguments}")
            self.process.setNativeArguments(self.spec.native_arguments)
        else:
            self.output.emit("system", "$ " + subprocess.list2cmdline([self.spec.program, *self.spec.args]))
        self.process.start(self.spec.program, self.spec.args)
        if self.spec.stdin is not None:
            self.process.write(self.spec.stdin.encode("utf-8"))
        self.process.closeWriteChannel()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def kill(self) -> None:
        """Kill the whole process tree (agents spawn shells, test runners, ...)."""
        if not self.is_running():
            return
        self.killed = True
        pid = self.process.processId()
        if sys.platform == "win32" and pid:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.process.kill()

    def _read(self, stream: str) -> None:
        raw = self.process.readAllStandardOutput() if stream == "stdout" else self.process.readAllStandardError()
        text = self._buffers[stream] + bytes(raw.data()).decode("utf-8", errors="replace")
        *lines, self._buffers[stream] = text.replace("\r\n", "\n").split("\n")
        for line in lines:
            self._emit_line(stream, line)

    def _emit_line(self, stream: str, line: str) -> None:
        if stream == "stderr":
            self.stderr_tail = (self.stderr_tail + [line])[-40:]
            self.output.emit("stdout" if self.adapter.progress_on_stderr else stream, line)
            return
        shown = self.adapter.format_output_line(line)
        if shown is not None:
            self.output.emit(stream, shown)

    def _flush(self) -> None:
        for stream in ("stdout", "stderr"):
            self._read(stream)
            if self._buffers[stream]:
                self._emit_line(stream, self._buffers[stream])
                self._buffers[stream] = ""

    def _on_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        if self._done:
            return
        self._done = True
        self._flush()
        crashed = self.killed or status == QProcess.ExitStatus.CrashExit
        self.finished.emit(exit_code, crashed)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and not self._done:
            self._done = True
            self.output.emit("system", f"Failed to start {self.spec.program}: {self.process.errorString()}")
            self.stderr_tail.append(self.process.errorString())
            self.finished.emit(-1, True)
