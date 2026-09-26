"""The dashboard row under the stage: Petty Scoreboard, Current Status, Recent Output, Project Files."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QDir, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..conversation import AGENTS
from ..theatre.banter import SCORE_ROWS, PettyScore
from ..theatre.cast import ACCENT, CHARACTER
from .avatar_paint import portrait_pixmap


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 8, 12, 10)
    layout.setSpacing(6)
    heading = QLabel(title)
    heading.setObjectName("panelTitle")
    layout.addWidget(heading)
    return frame, layout


class ScoreboardPanel(QFrame):
    """PETTY SCOREBOARD — only factual, derivable events; deliberately unserious."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        title = QLabel("🏆 PETTY SCOREBOARD")
        title.setObjectName("panelTitle")
        title.setToolTip("Counted from the public conversation only. Not a model leaderboard. Not a Weissman score.")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.values: dict[str, dict[str, QLabel]] = {}
        for agent in AGENTS:
            col = QGridLayout()
            col.setHorizontalSpacing(8)
            col.setVerticalSpacing(1)
            pic = QLabel()
            pic.setPixmap(portrait_pixmap(agent, 52))
            col.addWidget(pic, 0, 0, len(SCORE_ROWS) + 1, 1, Qt.AlignmentFlag.AlignTop)
            name = QLabel(CHARACTER[agent].upper())
            name.setStyleSheet(f"color:{ACCENT[agent]}; font-weight:800; letter-spacing:1px;")
            col.addWidget(name, 0, 1, 1, 2)
            self.values[agent] = {}
            for i, (key, label) in enumerate(SCORE_ROWS[:3], start=1):
                text = QLabel(label.replace(" by evidence", "").replace("Grudging concessions received",
                                                                          "Grudging concessions") + ":")
                text.setObjectName("dim")
                value = QLabel("0")
                value.setObjectName("scoreValue")
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                col.addWidget(text, i, 1)
                col.addWidget(value, i, 2)
                self.values[agent][key] = value
            holder = QWidget()
            holder.setLayout(col)
            row.addWidget(holder)
        layout.addLayout(row)
        layout.addStretch()
        foot = QLabel("counted from conversation.md · this is part of the joke")
        foot.setObjectName("footnote")
        layout.addWidget(foot)

    def set_scores(self, board: dict[str, PettyScore]) -> None:
        for agent, labels in self.values.items():
            score = board.get(agent)
            if score is None:
                continue
            for key, label in labels.items():
                label.setText(str(getattr(score, key)))


class StatusPanel(QFrame):
    def __init__(self, chips: list[QWidget], parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        title = QLabel("CURRENT STATUS")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(6)
        for chip in chips:
            row.addWidget(chip)
        row.addStretch()
        layout.addLayout(row)
        self.working = QLabel("")
        self.working.setObjectName("working")
        layout.addWidget(self.working)
        # An honest "busy" indicator: it shows that a process is running, not how far along it is.
        self.busy = QProgressBar()
        self.busy.setObjectName("busy")
        self.busy.setTextVisible(False)
        self.busy.setFixedHeight(6)
        self.busy.setRange(0, 1)
        layout.addWidget(self.busy)
        self.agent_row = QHBoxLayout()
        layout.addLayout(self.agent_row)
        layout.addStretch()

    def set_working(self, text: str, colour: str, busy: bool) -> None:
        self.working.setText(f'<span style="color:{colour}">●</span>&nbsp; {text}' if text else "")
        self.busy.setRange(0, 0 if busy else 1)
        self.busy.setStyleSheet(f"QProgressBar#busy::chunk {{ background:{colour}; border-radius:3px; }}")


class RecentOutputPanel(QFrame):
    """The last few raw CLI lines from whoever is working (full logs live in the raw output tabs)."""

    def __init__(self, parent=None, lines: int = 7):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        title = QLabel("RECENT OUTPUT")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        self.view = QPlainTextEdit()
        self.view.setObjectName("recentOutput")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.view)
        self._lines: deque[str] = deque(maxlen=lines)

    def add(self, agent: str, line: str) -> None:
        line = line.rstrip()
        if not line.strip():
            return
        tag = CHARACTER.get(agent, agent)[:1]
        self._lines.append(f"{tag}> {line[:220]}")
        self.view.setPlainText("\n".join(self._lines))


class FilesPanel(QFrame):
    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        title = QLabel("📁 PROJECT FILES")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(str(root))
        self.tree = QTreeView()
        self.tree.setObjectName("files")
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(root)))
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.doubleClicked.connect(self._open)
        layout.addWidget(self.tree)

    def _open(self, index) -> None:
        path = self.model.filePath(index)
        if path and not self.model.isDir(index):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
