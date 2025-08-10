# src/about_dialog.py
# 수정: v2.3.1의 기능에 맞춰 '주요 기능' 설명 텍스트 업데이트

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QTextBrowser, QWidget
)
from PyQt6.QtCore import Qt
from src.icon import get_app_icon
from src.utils import open_developer_link, open_feedback_link

class AboutDialog(QDialog):
    def __init__(self, version: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("정보")
        self.setWindowIcon(get_app_icon())
        self.setModal(True)
        self.setMinimumSize(640, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 상단 헤더
        header = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(get_app_icon().pixmap(32, 32))
        title_box = QVBoxLayout()
        title = QLabel("티버 다운로더"); title.setObjectName("PaneTitle")
        subtitle = QLabel(f"버전: {version}"); subtitle.setObjectName("PaneSubtitle")
        title_box.addWidget(title); title_box.addWidget(subtitle)
        header.addWidget(icon_label); header.addLayout(title_box); header.addStretch(1)
        root.addLayout(header)

        # 본문
        self.viewer = QTextBrowser(objectName="AboutViewer")
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setHtml(self._build_html())
        root.addWidget(self.viewer, 1)

        # 하단 버튼
        btn_row = QHBoxLayout()
        youtube_btn = QPushButton("제작자 유투브"); youtube_btn.setObjectName("LinkButton"); youtube_btn.clicked.connect(open_developer_link)
        contact_btn = QPushButton("문의하기"); contact_btn.setObjectName("LinkButton"); contact_btn.clicked.connect(open_feedback_link)
        btn_row.addWidget(youtube_btn); btn_row.addWidget(contact_btn); btn_row.addStretch(1)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        close_box.rejected.connect(self.reject)
        btn_row.addWidget(close_box)

        root.addLayout(btn_row)

    def _build_html(self) -> str:
        # v2.3.1 기준 핵심 기능 목록으로 업데이트
        return """
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { font-family: -apple-system, Segoe UI, Arial, sans-serif; font-size: 14px; }
                h3 { margin: 12px 0 6px 0; }
                ul { margin: 6px 0 12px 24px; list-style-type: disc; }
                li { margin: 6px 0; }
            </style>
        </head>
        <body>
            <p><b>티버 다운로더</b>는 TVer 콘텐츠를 합법적 범위 내 개인 용도로 다운로드하는 데 도움을 주는 데스크톱 앱입니다.</p>
            <p>지역 제한 서비스 특성상 일본 VPN 환경에서의 사용을 권장합니다.</p>

            <h3>주요 기능</h3>
            <ul>
                <li>에피소드/시리즈 URL 분석 및 일괄 다운로드</li>
                <li>다운로드 큐 및 동시 다운로드 수 제어</li>
                <li>즐겨찾기 시리즈 등록 및 신규 영상 자동 확인</li>
                <li>영상/오디오 품질 선택 및 자막 자동 병합</li>
                <li>사용자 정의 파일명 형식 지원</li>
                <li>다운로드 완료 후 자동 작업 (폴더 열기, 시스템 종료)</li>
                <li>썸네일 미리보기 (확대/저장) 및 다운로드 기록 관리</li>
                <li>단일 인스턴스 실행 (프로그램 중복 실행 방지)</li>
            </ul>

            <h3>오픈소스/레퍼런스</h3>
            <ul>
                <li><a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a></li>
                <li><a href="https://ffmpeg.org/">FFmpeg</a></li>
                <li><a href="https://pypi.org/project/PyQt6/">PyQt6</a></li>
                <li><a href="https://pypi.org/project/requests/">requests</a></li>
                <li><a href="https://github.com/deuxdoom/TVerDownloader">TVerDownloader (GitHub)</a></li>
            </ul>

            <p style="color:#6b7280;">* 사용자는 콘텐츠 제공자의 약관과 저작권을 준수해야 합니다.</p>
        </body>
        </html>
        """