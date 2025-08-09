# 파일명: src/qss.py
# 다크 테마 고정 버전. build_qss()는 항상 QSS_DARK를 반환.

QSS_DARK = r"""
/* 메인 프레임 */
QMainWindow { background-color: #101317; }
QFrame#AppHeader { background-color: #0f1720; border-bottom: 1px solid #1f2833; }
QFrame#InputBar  { background-color: #121925; border-bottom: 1px solid #1f2833; }
QStatusBar { background: transparent; color: #8aa1bd; }

/* 탭/스플리터 */
QSplitter#MainSplitter::handle { background: #0e141f; width: 6px; }
QTabWidget#MainTabs::pane { border: none; }
QTabBar::tab {
    background: #0f1720; color: #9fb5d1; padding: 10px 16px;
    border: 1px solid #1f2833; border-bottom: none;
}
QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }

/* 좌/우 패널 */
QFrame#LeftPane, QFrame#RightPane, QWidget#HistoryTab, QWidget#FavoritesTab { background-color: #0d131c; }
QLabel#AppTitle { color: #e6edf3; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
QLabel#PaneTitle { color: #dbe6f3; font-size: 14px; font-weight: 600; }
QLabel#PaneSubtitle { color: #94a3b8; font-size: 12px; }
QLabel { color: #dbe6f3; }

/* 체크박스 — ✔ 기본 사용(인디케이터 스타일 없음) */
QCheckBox {
    color: #dbe6f3;
    padding: 2px 0;
    background: transparent;
    border: none;
}

/* 입력창 */
QLineEdit#UrlInput {
    background: #0b1220; border: 1px solid #233044; border-radius: 8px;
    padding: 10px 12px; color: #e6edf3; selection-background-color: #1c64f2;
}
QLineEdit#UrlInput:focus { border: 1px solid #3b82f6; }
QLineEdit:disabled { background: #0f1522; color: #7a8699; border: 1px solid #1f2833; }

/* 버튼 */
QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#GhostButton {
    border-radius: 8px; padding: 8px 14px; font-weight: 600;
}
QPushButton#PrimaryButton { background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c; }
QPushButton#PrimaryButton:hover, QPushButton#PrimaryButton:focus { background: #263444; }
QPushButton#AccentButton { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
QPushButton#AccentButton:hover, QPushButton#AccentButton:focus { background: #1d4ed8; }
QPushButton#GhostButton { background: transparent; color: #9fb5d1; border: 1px solid #2b3a4c; }
QPushButton#GhostButton:hover, QPushButton#GhostButton:focus { background: #17202b; }
QPushButton:disabled { background: #1b2430; color: #7a8699; border: 1px solid #2b3a4c; }

/* 리스트/로그 */
QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {
    background: #0d131c; border: 1px solid #1f2833; border-radius: 10px;
}
QListWidget#DownloadList::item, QListWidget#HistoryList::item, QListWidget#FavoritesList::item { color: #dbe6f3; padding: 6px 8px; }
QListWidget#DownloadList::item:hover, QListWidget#HistoryList::item:hover, QListWidget#FavoritesList::item:hover { background: #111a26; }
QListWidget#DownloadList::item:selected, QListWidget#HistoryList::item:selected, QListWidget#FavoritesList::item:selected { background: #17202b; color: #ffffff; }

QTextEdit#LogOutput {
    background: #0b1220; color: #9fb5d1; border: 1px solid #1f2833; border-radius: 10px;
    font-family: Consolas, "Courier New", monospace; font-size: 12px;
    selection-background-color: #1c64f2; selection-color: #ffffff;
}

/* 진행바 */
QProgressBar { border: none; background: #0e1726; height: 12px; border-radius: 6px; text-align: center; color: #e6edf3; }
QProgressBar::chunk { background-color: #3b82f6; border-radius: 6px; }

/* 원형 '항상 위' 버튼 */
QToolButton#OnTopButton {
    background: #1f2a37; border: 1px solid #2b3a4c; border-radius: 14px;
    width: 28px; height: 28px; color: #e6edf3; font-weight: 700; font-size: 14px;
}
QToolButton#OnTopButton:hover, QToolButton#OnTopButton:focus { background: #263444; }
QToolButton#OnTopButton:checked { background: #2563eb; border-color: #1d4ed8; color: #ffffff; }

/* QDialog 공통 */
QDialog { background-color: #0d131c; color: #dbe6f3; }
QDialog QLabel { color: #dbe6f3; }
QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox {
    background: #0b1220; color: #e6edf3; border: 1px solid #233044; border-radius: 6px; padding: 6px 8px;
}
QDialog QLineEdit:focus, QDialog QComboBox:focus, QDialog QSpinBox:focus { border: 1px solid #3b82f6; }
QDialog QAbstractItemView {
    background: #0b1220; color: #e6edf3; border: 1px solid #1f2833;
    selection-background-color: #3b82f6; selection-color: #ffffff;
}
QDialog QListWidget { background: #0b1220; border: 1px solid #1f2833; border-radius: 8px; }
QDialog QListWidget::item { color: #e6f0ff; }

/* 다이얼로그 버튼/탭 */
QDialog QPushButton {
    background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c;
    padding: 6px 12px; border-radius: 6px; min-width: 72px;
}
QDialog QPushButton:hover, QDialog QPushButton:focus { background: #263444; }
QDialog QTabWidget::pane { background: #0f1720; border: 1px solid #1f2833; border-radius: 8px; }
QDialog QTabBar::tab {
    background: #0f1720; color: #9fb5d1; padding: 8px 12px; border: 1px solid #1f2833; border-bottom: none;
}
QDialog QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }

/* 메시지 박스 */
QMessageBox { background-color: #121925; border: 1px solid #1f2833; }
QMessageBox QLabel { color: #dbe6f3; }
QMessageBox QPushButton {
    background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c;
    padding: 6px 12px; border-radius: 6px; min-width: 72px;
}
QMessageBox QPushButton:hover { background: #263444; }
QMessageBox QPushButton:default { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }

/* 메뉴/툴팁 */
QMenu { background: #0b1220; color: #e6edf3; border: 1px solid #1f2833; }
QMenu::item { padding: 6px 12px; }
QMenu::item:selected { background: #1a2230; }
QMenu::separator { height: 1px; background: #1f2833; margin: 4px 8px; }
QToolTip { background: #0b1220; color: #e6edf3; border: 1px solid #1f2833; padding: 6px 8px; }

/* 스크롤바 */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2b3a4c; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2b3a4c; min-width: 24px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* About 뷰어 */
QDialog QTextBrowser#AboutViewer {
    background: #0b1220; color: #dbe6f3;
    border: 1px solid #1f2833; border-radius: 8px; padding: 8px;
    selection-background-color: #1c64f2; selection-color: #ffffff;
}
"""

def build_qss(_theme: str | None = None) -> str:
    """항상 다크 테마 반환."""
    return QSS_DARK
