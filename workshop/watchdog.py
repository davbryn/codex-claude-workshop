"""Freeze diagnostics: if the UI thread stops responding, record where every thread is.

A QTimer on the UI thread updates a heartbeat twice a second. A background
thread checks it; if the UI has been silent for ``stall_s`` seconds, it writes
every thread's Python stack (faulthandler) to ``freeze-<time>.log``, once per
freeze. Crashes are also recorded there via faulthandler.
"""

from __future__ import annotations

import faulthandler
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer


class FreezeWatchdog(QObject):
    def __init__(self, log_dir: Path, stall_s: float = 8.0, parent: QObject | None = None):
        super().__init__(parent)
        self.log_dir = Path(log_dir)
        self.stall_s = stall_s
        self._beat = time.monotonic()
        self._stop = threading.Event()
        self._dumped = False
        self.dumps: list[Path] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._heartbeat)
        self._timer.start(500)
        self._crash_file = None
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._crash_file = open(self.log_dir / "crash.log", "a", encoding="utf-8")
            faulthandler.enable(self._crash_file, all_threads=True)
        except OSError:
            pass
        self._thread = threading.Thread(target=self._watch, name="freeze-watchdog", daemon=True)
        self._thread.start()

    def _heartbeat(self) -> None:
        self._beat = time.monotonic()
        self._dumped = False

    def _watch(self) -> None:
        while not self._stop.wait(1.0):
            silent = time.monotonic() - self._beat
            if silent > self.stall_s and not self._dumped:
                self._dumped = True
                self._dump(silent)

    def _dump(self, silent: float) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"freeze-{time.strftime('%Y%m%d-%H%M%S')}.log"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"The UI thread has not responded for {silent:.1f}s. Stacks of every thread:\n\n")
                f.flush()
                faulthandler.dump_traceback(f, all_threads=True)
            self.dumps.append(path)
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        self._timer.stop()
        if self._crash_file is not None:
            try:
                faulthandler.disable()
                self._crash_file.close()
            except (OSError, ValueError):
                pass
