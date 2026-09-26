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
