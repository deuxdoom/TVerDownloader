# -*- coding: utf-8 -*-
# 파일명: src/qss.py
# 역할: 앱 전역 스타일(QSS) 생성
#
# 콘셉트: 고급스러운 다크 그레이 톤 + 포인트 컬러
# - 텍스트/배경: #0B0B0C ~ #1C1C1E 계열
# - 기본 포인트(진행/강조): 파란색 #3B82F6
# - 완료: 녹색 #22C55E
# - 위험/오류: 빨간 #EF4444
#
# 진행바는 동적 프로퍼티 state(active/done/error)로 색상 전환

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

    /* 버튼 */
    QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#DangerButton, QPushButton#GhostButton {
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid transparent;
        font-weight: 600;
    }
    QPushButton#PrimaryButton {
        background: #1F2937;
        color: #E5E7EB;
    }
    QPushButton#AccentButton {
        background: #3B82F6;
        color: white;
    }
    QPushButton#DangerButton {
        background: #EF4444;
        color: white;
    }
    QPushButton#GhostButton {
        background: transparent;
        color: #9CA3AF;
        border-color: #374151;
    }
    QPushButton:hover {
        filter: brightness(1.05);
    }
    QPushButton:disabled {
        opacity: .6;
    }

    /* 입력 */
    QLineEdit#UrlInput {
        background: #111214;
        border: 1px solid #30343C;
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: #3B82F6;
        selection-color: white;
    }

    /* 탭/패널 */
    #MainTabs::pane {
        border: none;
    }
    #LeftPane, #RightPane, #DownloadTab, #HistoryTab, #FavoritesTab {
        background: #0F0F10;
    }
    #PaneTitle {
        color: #E5E7EB;
        font-weight: 600;
    }
    #PaneSubtitle {
        color: #9CA3AF;
    }

    /* 리스트 */
    QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {
        background: #0F0F10;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 6px;
    }

    /* 다운로드 아이템 */
    #DownloadItem {
        background: #111214;
        border: 1px solid #1F2937;
        border-radius: 10px;
    }
    #DownloadItem:hover {
        border-color: #334155;
    }
    QLabel#Title {
        font-weight: 600;
        color: #F3F4F6;
    }
    QLabel#Status {
        color: #9CA3AF;
    }
    QLabel#Thumb {
        background: #0B0B0C;
        border: 1px solid #22262E;
        border-radius: 6px;
    }

    /* 진행바: 상태별 색상 */
    QProgressBar#Progress {
        background: #0B0B0C;
        border: 1px solid #1F2937;
        border-radius: 7px;
        min-height: 14px;
    }
    QProgressBar#Progress::chunk {
        border-radius: 7px;
        background: #3B82F6; /* 기본 */
    }
    QProgressBar#Progress[state="active"]::chunk {
        background: #3B82F6; /* 진행 중: 파랑 */
    }
    QProgressBar#Progress[state="done"]::chunk {
        background: #22C55E; /* 완료: 초록 */
    }
    QProgressBar#Progress[state="error"]::chunk {
        background: #EF4444; /* 오류/취소: 빨강 */
    }

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
