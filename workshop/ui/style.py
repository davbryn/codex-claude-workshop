STYLESHEET = """
QWidget { background: #14171c; color: #d7dce4; font-family: "Segoe UI"; font-size: 10pt; }
QDialog, QMainWindow { background: #14171c; }
QLabel#title { font-size: 18pt; font-weight: 800; letter-spacing: 3px; color: #f2f4f8; padding: 4px; }
QLabel#subtitle { color: #8b93a1; }
QLabel#modeTag { background: #6b4cd6; color: white; font-weight: bold; padding: 2px 8px; border-radius: 4px; }
QFrame#agentPanel { background: #1b1f26; border-radius: 12px; }
QFrame#agentPanel QLabel { background: transparent; }
QLabel#agentName { font-size: 16pt; font-weight: 800; letter-spacing: 4px; background: transparent; }
QLabel#agentState { font-size: 11pt; font-weight: 700; background: transparent; }
QLabel#agentTurns { color: #8b93a1; background: transparent; }
QFrame#agentPanel QLabel#speechBubble {
    background: #262c36; border: 1px solid #3a414c; border-radius: 12px;
    padding: 10px 12px; font-size: 10.5pt; color: #eef1f5;
}
QFrame#agentPanel QLabel#speechBubble[placeholder="true"] { color: #7d8594; font-style: italic; }
QLabel#liveOutput { color: #7d8594; font-family: Consolas, monospace; font-size: 8.5pt; background: transparent; }
QFrame#agentPanel QLabel#disagreeBadge {
    background: #5c1f24; color: #ffb3b3; font-weight: 800; border-radius: 6px; padding: 3px; letter-spacing: 1px;
}
QLabel#banner { border-radius: 6px; padding: 8px 12px; font-weight: 600; }
QLabel#warningText { color: #f5c542; }
QPlainTextEdit, QTextBrowser, QLineEdit {
    background: #0f1216; border: 1px solid #2c323c; border-radius: 6px; color: #d7dce4;
    selection-background-color: #3d5a80;
}
QPlainTextEdit#rawOutput { font-family: Consolas, monospace; font-size: 9pt; }
QPushButton, QToolButton {
    background: #262c36; border: 1px solid #3a414c; border-radius: 6px; padding: 6px 14px; color: #e6e9ef;
}
QPushButton:hover, QToolButton:hover { background: #313845; }
QPushButton:disabled { color: #5d6470; background: #1b1f26; }
QPushButton#startButton { background: #2f6f4f; border-color: #39d98a; font-weight: bold; padding: 8px 22px; }
QPushButton#stopButton { border-color: #a04545; }
QTabWidget::pane { border: 1px solid #2c323c; border-radius: 6px; }
QTabBar::tab { background: #1b1f26; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #2a303a; color: white; }
QComboBox { background: #262c36; border: 1px solid #3a414c; border-radius: 6px; padding: 4px 8px; }
QGroupBox { border: 1px solid #2c323c; border-radius: 6px; margin-top: 4px; padding: 8px; }
QRadioButton::indicator { width: 10px; height: 10px; border: 1px solid #8b93a1; border-radius: 6px; background: #0f1216; }
QRadioButton::indicator:checked { background: #39d98a; border-color: #39d98a; }
QStatusBar { color: #8b93a1; }
QSplitter::handle { background: #14171c; }
"""

STYLESHEET += """
QFrame#statusStrip { background: #10141b; border: 1px solid #242b36; border-radius: 10px; }
QFrame#statusStrip QLabel { background: transparent; }
QLabel#chip {
    background: #1a2029; border: 1px solid #2a323e; border-radius: 9px; padding: 2px 9px;
    color: #c9d1d9; font-size: 9.5pt;
}
QLabel#popcorn { font-size: 13pt; background: transparent; }
QToolButton#toggle { padding: 3px 10px; border-radius: 8px; background: #1a2029; }
QToolButton#toggle:checked { background: #2a2230; border-color: #6b4c7a; }
QLabel#title { font-size: 17pt; }
"""

# --- Hacker-house theme (Gilfoyle & Dinesh) --------------------------------------
STYLESHEET += """
QWidget { background: #13110f; color: #ddd5c8; }
QDialog, QMainWindow { background: #13110f; }
QFrame#headerBar { background: #1a1714; border: 1px solid #2b2621; border-radius: 8px; }
QFrame#headerBar QLabel { background: transparent; }
QLabel#title { font-size: 15pt; font-weight: 800; letter-spacing: 2px; color: #efe8dc; padding: 2px; }
QLabel#headerDim { color: #9a9185; font-size: 10pt; }
QLabel#sep { color: #3a342e; background: transparent; border: none; padding: 0; }
QLabel#live { font-weight: 800; letter-spacing: 1px; color: #e6dfd3; padding-right: 6px; }
QLabel#modeTag { background: #8c1d1d; color: #ffe9e6; font-weight: bold; padding: 2px 8px; border-radius: 4px; }
QFrame#panel { background: #1a1714; border: 1px solid #2b2621; border-radius: 8px; }
QFrame#panel QLabel, QFrame#panel QWidget { background: transparent; }
QLabel#panelTitle { color: #efe8dc; font-weight: 800; letter-spacing: 1.5px; font-size: 10.5pt; }
QLabel#dim { color: #9a9185; }
QLabel#scoreValue { color: #efe8dc; font-weight: 700; min-width: 18px; }
QLabel#footnote { color: #6b645b; font-size: 8.5pt; font-style: italic; }
QLabel#working { color: #e6dfd3; font-size: 10.5pt; }
QProgressBar#busy { background: #2a2520; border: none; border-radius: 3px; }
QPlainTextEdit#recentOutput {
    background: #0c0b0a; border: 1px solid #2b2621; color: #b9d8b6;
    font-family: Consolas, monospace; font-size: 8.8pt;
}
QTreeView#files { background: #0f0d0c; border: 1px solid #2b2621; border-radius: 6px; color: #ddd5c8; }
QTreeView#files::item:selected { background: #3a2a22; }
QPlainTextEdit, QTextBrowser, QLineEdit { background: #0f0d0c; border: 1px solid #2b2621; color: #ddd5c8; }
QPushButton, QToolButton { background: #221e1a; border: 1px solid #3a332c; color: #eee6da; }
QPushButton:hover, QToolButton:hover { background: #2d2722; }
QPushButton:disabled { color: #5d564e; background: #191613; }
QPushButton#pauseButton { background: #a8322b; border-color: #d0453b; color: white; font-weight: 700; padding: 8px 18px; }
QPushButton#pauseButton:hover { background: #bf3b33; }
QPushButton#pauseButton:disabled { background: #2a2320; border-color: #3a332c; color: #8b8378; }
QPushButton#stopButton { border-color: #7a3a33; }
QLineEdit#messageBox { padding: 7px 10px; font-size: 10.5pt; border-radius: 8px; }
QToolButton#sendButton { font-size: 13pt; padding: 3px 12px; border-radius: 8px; }
QToolButton#toggle { padding: 3px 10px; border-radius: 8px; background: #221e1a; }
QToolButton#toggle:checked { background: #3a2226; border-color: #7a3a33; }
QTabWidget::pane { border: 1px solid #2b2621; border-radius: 6px; }
QTabBar::tab { background: #1a1714; padding: 6px 14px; color: #9a9185; font-weight: 700; letter-spacing: 1px; }
QTabBar::tab:selected { background: #26211c; color: #efe8dc; }
QComboBox { background: #221e1a; border: 1px solid #3a332c; }
QLabel#chip { background: #221e1a; border: 1px solid #332d27; color: #ddd5c8; }
QStatusBar { color: #9a9185; }
QSplitter::handle { background: #13110f; }
"""
