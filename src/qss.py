# 파일명: src/qss.py

QSS_DARK = r"""
QMainWindow { background-color: #101317; }
QFrame#AppHeader { background-color: #0f1720; border-bottom: 1px solid #1f2833; }
QFrame#InputBar  { background-color: #121925; border-bottom: 1px solid #1f2833; }
QStatusBar { background: transparent; color: #8aa1bd; }

QSplitter#MainSplitter::handle { background: #0e141f; width: 6px; }
QTabWidget#MainTabs::pane { border: none; }
QTabBar::tab { background: #0f1720; color: #9fb5d1; padding: 10px 16px; border: 1px solid #1f2833; border-bottom: none; }
QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }

QFrame#LeftPane, QFrame#RightPane, QWidget#HistoryTab { background-color: #0d131c; }
QLabel#AppTitle { color: #e6edf3; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
QLabel#PaneTitle { color: #dbe6f3; font-size: 14px; font-weight: 600; }
QLabel#PaneSubtitle { color: #94a3b8; font-size: 12px; }
QLabel { color: #dbe6f3; }

QLineEdit#UrlInput { background: #0b1220; border: 1px solid #233044; border-radius: 8px; padding: 10px 12px; color: #e6edf3; selection-background-color: #1c64f2; }
QLineEdit#UrlInput:focus { border: 1px solid #3b82f6; }
QLineEdit:disabled { background: #0f1522; color: #7a8699; border: 1px solid #1f2833; }

QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#GhostButton { border-radius: 8px; padding: 8px 14px; font-weight: 600; }
QPushButton#PrimaryButton { background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c; }
QPushButton#PrimaryButton:hover, QPushButton#PrimaryButton:focus { background: #263444; }
QPushButton#AccentButton { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
QPushButton#AccentButton:hover, QPushButton#AccentButton:focus { background: #1d4ed8; }
QPushButton#GhostButton { background: transparent; color: #9fb5d1; border: 1px solid #2b3a4c; }
QPushButton#GhostButton:hover, QPushButton#GhostButton:focus { background: #17202b; }
QPushButton:disabled { background: #1b2430; color: #7a8699; border: 1px solid #2b3a4c; }

QListWidget#DownloadList, QListWidget#HistoryList { background: #0d131c; border: 1px solid #1f2833; border-radius: 10px; }
QListWidget#DownloadList::item, QListWidget#HistoryList::item { color: #dbe6f3; padding: 8px 10px; }  /* 간격 +2 */
QListWidget#DownloadList::item:hover, QListWidget#HistoryList::item:hover { background: #111a26; }
QListWidget#DownloadList::item:selected, QListWidget#HistoryList::item:selected { background: #17202b; color: #ffffff; }

QTextEdit#LogOutput { background: #0b1220; color: #9fb5d1; border: 1px solid #1f2833; border-radius: 10px; font-family: Consolas, "Courier New", monospace; font-size: 12px; selection-background-color: #1c64f2; selection-color: #ffffff; }

QProgressBar { border: none; background: #0e1726; height: 12px; border-radius: 6px; text-align: center; color: #e6edf3; }
QProgressBar::chunk { background-color: #3b82f6; border-radius: 6px; }

QToolButton#OnTopButton { background: #1f2a37; border: 1px solid #2b3a4c; border-radius: 14px; width: 28px; height: 28px; color: #e6edf3; font-weight: 700; font-size: 14px; }
QToolButton#OnTopButton:hover, QToolButton#OnTopButton:focus { background: #263444; }
QToolButton#OnTopButton:checked { background: #2563eb; border-color: #1d4ed8; color: #ffffff; }

QDialog { background-color: #0d131c; color: #dbe6f3; }
QDialog QLabel { color: #dbe6f3; }
QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox { background: #0b1220; color: #e6edf3; border: 1px solid #233044; border-radius: 6px; padding: 6px 8px; }
QDialog QLineEdit:focus, QDialog QComboBox:focus, QDialog QSpinBox:focus { border: 1px solid #3b82f6; }
QDialog QAbstractItemView { background: #0b1220; color: #e6edf3; border: 1px solid #1f2833; selection-background-color: #3b82f6; selection-color: #ffffff; }
QDialog QListWidget { background: #0b1220; border: 1px solid #1f2833; border-radius: 8px; }
QDialog QListWidget::item { color: #e6f0ff; padding: 8px 10px; }  /* 간격 +2 */
/* QDialog QCheckBox 스타일 규칙 삭제됨(✔ OS 기본 사용) */

QDialog QPushButton { background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c; padding: 6px 12px; border-radius: 6px; min-width: 72px; }
QDialog QPushButton:hover, QDialog QPushButton:focus { background: #263444; }
QDialog QTabWidget::pane { background: #0f1720; border: 1px solid #1f2833; border-radius: 8px; }
QDialog QTabBar::tab { background: #0f1720; color: #9fb5d1; padding: 8px 12px; border: 1px solid #1f2833; border-bottom: none; }
QDialog QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }

QMessageBox { background-color: #121925; border: 1px solid #1f2833; }
QMessageBox QLabel { color: #dbe6f3; }
QMessageBox QPushButton { background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c; padding: 6px 12px; border-radius: 6px; min-width: 72px; }
QMessageBox QPushButton:hover { background: #263444; }
QMessageBox QPushButton:default { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }

QMenu { background: #0b1220; color: #e6edf3; border: 1px solid #1f2833; }
QMenu::item { padding: 6px 12px; }
QMenu::item:selected { background: #1a2230; }
QMenu::separator { height: 1px; background: #1f2833; margin: 4px 8px; }
QToolTip { background: #0b1220; color: #e6edf3; border: 1px solid #1f2833; padding: 6px 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2b3a4c; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2b3a4c; min-width: 24px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QDialog QTextBrowser#AboutViewer { background: #0b1220; color: #dbe6f3; border: 1px solid #1f2833; border-radius: 8px; padding: 8px; selection-background-color: #1c64f2; selection-color: #ffffff; }
"""

QSS_LIGHT = r"""
QMainWindow { background-color: #f6f7fb; }
QFrame#AppHeader { background-color: #ffffff; border-bottom: 1px solid #e9edf3; }
QFrame#InputBar  { background-color: #ffffff; border-bottom: 1px solid #e9edf3; }
QStatusBar { background: transparent; color: #6b7280; }

QSplitter#MainSplitter::handle { background: #eef1f6; width: 6px; }
QTabWidget#MainTabs::pane { border: none; }
QTabBar::tab { background: #ffffff; color: #6b7280; padding: 10px 16px; border: 1px solid #e9edf3; border-bottom: none; }
QTabBar::tab:selected { background: #f9fafc; color: #111827; }

QFrame#LeftPane, QFrame#RightPane, QWidget#HistoryTab { background-color: #f9fafc; }
QLabel#AppTitle { color: #171a21; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
QLabel#PaneTitle { color: #1f2937; font-size: 14px; font-weight: 600; }
QLabel#PaneSubtitle { color: #6b7280; font-size: 12px; }
QLabel { color: #1f2937; }

QLineEdit#UrlInput { background: #ffffff; border: 1px solid #dbe2ea; border-radius: 8px; padding: 10px 12px; color: #111827; selection-background-color: #2563eb; }
QLineEdit#UrlInput:focus { border: 1px solid #2563eb; }
QLineEdit:disabled { background: #f7f8fb; color: #9ca3af; border: 1px solid #e5e7eb; }

QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#GhostButton { border-radius: 8px; padding: 8px 14px; font-weight: 600; }
QPushButton#PrimaryButton { background: #eef2f7; color: #111827; border: 1px solid #e3e8ef; }
QPushButton#PrimaryButton:hover, QPushButton#PrimaryButton:focus { background: #e4e9f1; }
QPushButton#AccentButton { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
QPushButton#AccentButton:hover, QPushButton#AccentButton:focus { background: #1d4ed8; }
QPushButton#GhostButton { background: transparent; color: #374151; border: 1px solid #e3e8ef; }
QPushButton#GhostButton:hover, QPushButton#GhostButton:focus { background: #eef2f7; }
QPushButton:disabled { background: #f3f4f6; color: #9ca3af; border: 1px solid #e5e7eb; }

QListWidget#DownloadList, QListWidget#HistoryList { background: #ffffff; border: 1px solid #e9edf3; border-radius: 10px; }
QListWidget#DownloadList::item, QListWidget#HistoryList::item { color: #111827; padding: 8px 10px; }
QListWidget#DownloadList::item:hover, QListWidget#HistoryList::item:hover { background: #f2f6ff; }
QListWidget#DownloadList::item:selected, QListWidget#HistoryList::item:selected { background: #e8efff; color: #0b1742; }

QTextEdit#LogOutput { background: #ffffff; color: #334155; border: 1px solid #e9edf3; border-radius: 10px; font-family: Consolas, "Courier New", monospace; font-size: 12px; selection-background-color: #2563eb; selection-color: #ffffff; }

QProgressBar { border: none; background: #eef2f7; height: 12px; border-radius: 6px; text-align: center; color: #111827; }
QProgressBar::chunk { background-color: #2563eb; border-radius: 6px; }

QToolButton#OnTopButton { background: #eef2f7; border: 1px solid #e3e8ef; border-radius: 14px; width: 28px; height: 28px; color: #111827; font-weight: 700; font-size: 14px; }
QToolButton#OnTopButton:hover, QToolButton#OnTopButton:focus { background: #e4e9f1; }
QToolButton#OnTopButton:checked { background: #2563eb; border-color: #1d4ed8; color: #ffffff; }

QDialog { background-color: #ffffff; color: #111827; }
QDialog QLabel { color: #1f2937; }
QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox { background: #ffffff; color: #111827; border: 1px solid #dbe2ea; border-radius: 6px; padding: 6px 8px; }
QDialog QLineEdit:focus, QDialog QComboBox:focus, QDialog QSpinBox:focus { border: 1px solid #2563eb; }
QDialog QAbstractItemView { background: #ffffff; color: #111827; border: 1px solid #e3e8ef; selection-background-color: #2563eb; selection-color: #ffffff; }
QDialog QListWidget { background: #ffffff; border: 1px solid #e9edf3; border-radius: 8px; }
QDialog QListWidget::item { color: #111827; padding: 8px 10px; }
/* QDialog QCheckBox 스타일 규칙 삭제됨(✔ OS 기본 사용) */

QDialog QPushButton { background: #eef2f7; color: #111827; border: 1px solid #e3e8ef; padding: 6px 12px; border-radius: 6px; min-width: 72px; }
QDialog QPushButton:hover, QDialog QPushButton:focus { background: #e4e9f1; }
QDialog QTabWidget::pane { background: #ffffff; border: 1px solid #e9edf3; border-radius: 8px; }
QDialog QTabBar::tab { background: #ffffff; color: #6b7280; padding: 8px 12px; border: 1px solid #e9edf3; border-bottom: none; }
QDialog QTabBar::tab:selected { background: #f9fafa; color: #111827; }

QMessageBox { background-color: #ffffff; border: 1px solid #e9edf3; }
QMessageBox QLabel { color: #111827; }
QMessageBox QPushButton { background: #eef2f7; color: #111827; border: 1px solid #e3e8ef; padding: 6px 12px; border-radius: 6px; min-width: 72px; }
QMessageBox QPushButton:hover { background: #e4e9f1; }
QMessageBox QPushButton:default { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }

QMenu { background: #ffffff; color: #111827; border: 1px solid #e9edf3; }
QMenu::item { padding: 6px 12px; }
QMenu::item:selected { background: #e8efff; }
QMenu::separator { height: 1px; background: #e9edf3; margin: 4px 8px; }
QToolTip { background: #ffffff; color: #111827; border: 1px solid #dbe2ea; padding: 6px 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #cbd5e1; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #cbd5e1; min-width: 24px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QDialog QTextBrowser#AboutViewer { background: #ffffff; color: #111827; border: 1px solid #e9edf3; border-radius: 8px; padding: 8px; selection-background-color: #2563eb; selection-color: #ffffff; }
"""

def build_qss(theme: str) -> str:
    return QSS_DARK if theme == "dark" else QSS_LIGHT
