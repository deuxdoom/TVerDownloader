# src/qss.py
# 수정: QToolButton#OnTopButton 스타일 규칙 변경
#      - 기본 상태(비활성화)에서는 회색 아이콘
#      - 체크 상태(활성화)에서는 파란색 아이콘으로 표시

def build_qss() -> str:
    return """
    /* 기본 */
    QWidget {
        background: #0F0F10;
        color: #E5E7EB;
        font-size: 13px;
    }
    QMainWindow, QDialog {
        background: #0F0F10;
    }
    #AppHeader {
        background: #121214;
        border-bottom: 1px solid #1F2937;
    }
    #AppTitle {
        font-size: 16px;
        font-weight: 600;
        color: #F3F4F6;
    }

    /* 버튼 공통 스타일 */
    QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#DangerButton, 
    QPushButton#GhostButton, QPushButton#OrangeButton, QPushButton#PurpleButton {
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid transparent;
        font-weight: 600;
    }
    QPushButton:hover {
        filter: brightness(1.05);
    }
    QPushButton:disabled {
        opacity: .6;
    }

    /* 버튼 개별 색상 */
    QPushButton#PrimaryButton { background: #1F2937; color: #E5E7EB; }
    QPushButton#AccentButton { background: #3B82F6; color: white; }
    QPushButton#DangerButton { background: #EF4444; color: white; }
    QPushButton#GhostButton { background: transparent; color: #9CA3AF; border-color: #374151; }
    QPushButton#OrangeButton { background: #F97316; color: white; }
    QPushButton#PurpleButton { background: #8B5CF6; color: white; }

    /* '항상 위' 버튼 스타일 */
    QToolButton#OnTopButton {
        background: transparent;
        border: none;
        font-size: 16px;
        padding: 2px;
        color: #9CA3AF; /* 비활성화(기본) 상태 아이콘 색상: 회색 */
    }
    QToolButton#OnTopButton:hover {
        background: #374151;
        border-radius: 4px;
    }
    QToolButton#OnTopButton:checked {
        background: transparent;
        color: #3B82F6; /* 활성화 상태 아이콘 색상: 파란색 */
    }

    /* 입력 */
    QLineEdit#UrlInput {
        background: #111214;
        border: 1px solid #FFFFFF;
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: #3B82F6;
        selection-color: white;
    }
    QLineEdit#UrlInput:focus {
        border: 1px solid #3B82F6;
    }

    /* 탭/패널 */
    #MainTabs::pane { border: none; }
    #LeftPane, #RightPane, #DownloadTab, #HistoryTab, #FavoritesTab { background: #0F0F10; }
    #PaneTitle { color: #E5E7EB; font-weight: 600; }
    #PaneSubtitle { color: #9CA3AF; }

    /* 리스트 */
    QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {
        background: #0F0F10;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 6px;
    }

    /* 다운로드 아이템 */
    #DownloadItem { background: #111214; border: 1px solid #1F2937; border-radius: 10px; }
    #DownloadItem:hover { border-color: #334155; }
    QLabel#Title { font-weight: 600; color: #F3F4F6; }
    QLabel#Status { color: #9CA3AF; }
    QLabel#Thumb { background: #0B0B0C; border: 1px solid #22262E; border-radius: 6px; }

    /* 진행바: 상태별 색상 */
    QProgressBar#Progress {
        background: #0B0B0C;
        border: 1px solid #1F2937;
        border-radius: 7px;
        min-height: 14px;
        max-height: 14px;
    }
    QProgressBar#Progress::chunk { border-radius: 7px; background: #3B82F6; }
    QProgressBar#Progress[state="active"]::chunk { background: #3B82F6; }
    QProgressBar#Progress[state="done"]::chunk { background: #22C55E; }
    QProgressBar#Progress[state="error"]::chunk { background: #EF4444; }

    /* 텍스트 에디트(로그) */
    #LogOutput {
        background: #0B0B0C;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 8px;
        selection-background-color: #3B82F6;
        selection-color: white;
    }
    """