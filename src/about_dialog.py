# 파일명: src/about_dialog.py
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
        self.setWindowTitle("정보 - 티버 다운로더 (TVer Downloader)")
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
        title = QLabel("티버 다운로더 (TVer Downloader)"); title.setObjectName("PaneTitle")
        subtitle = QLabel(f"버전: {version}"); subtitle.setObjectName("PaneSubtitle")
        title_box.addWidget(title); title_box.addWidget(subtitle)
        header.addWidget(icon_label); header.addLayout(title_box); header.addStretch(1)
        root.addLayout(header)

        # 본문
        self.viewer = QTextBrowser(objectName="AboutViewer")
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setHtml(self._build_html(version))
        root.addWidget(self.viewer, 1)

        # 하단 버튼
        btn_row = QHBoxLayout()
        youtube_btn = QPushButton("유투브"); youtube_btn.setObjectName("LinkButton"); youtube_btn.clicked.connect(open_developer_link)
        contact_btn = QPushButton("문의하기"); contact_btn.setObjectName("LinkButton"); contact_btn.clicked.connect(open_feedback_link)
        btn_row.addWidget(youtube_btn); btn_row.addWidget(contact_btn); btn_row.addStretch(1)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        btn_row.addWidget(close_box)

        root.addLayout(btn_row)

    def _build_html(self, version: str) -> str:
        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; font-size: 14px; }}
                h3 {{ margin: 12px 0 6px 0; }}
                ul {{ margin: 6px 0 12px 24px; }}
                li {{ margin: 4px 0; }}
            </style>
        </head>
        <body>
            <p><b>티버 다운로더</b>는 TVer 콘텐츠를 합법적 범위 내 개인 용도로 다운로드하는 데 도움을 주는 데스크톱 앱입니다.</p>
            <p>지역 제한 서비스 특성상 일본 VPN 환경에서의 사용을 권장합니다.</p>

            <h3>주요 기능</h3>
            <ul>
                <li>에피소드/시리즈 URL 분석 및 일괄 다운로드</li>
                <li>진행률/속도/ETA, 자막 임베드(가능 시)</li>
                <li>파일명 커스터마이즈, 동시 다운로드 수 조절</li>
                <li>기록 탭: 재다운로드/제거</li>
                <li>GitHub 최신 버전 확인 알림</li>
            </ul>

            <h3>오픈소스/레퍼런스</h3>
            <ul>
                <li><a href="https://github.com/yt-dlp/yt-dlp-nightly-builds">yt-dlp nightly builds</a></li>
                <li><a href="https://github.com/GyanD/codexffmpeg">FFmpeg for Windows (GyanD)</a></li>
                <li><a href="https://pypi.org/project/PyQt6/">PyQt6</a></li>
                <li><a href="https://pypi.org/project/requests/">requests</a></li>
                <li><a href="https://github.com/deuxdoom/TVerDownloader">TVerDownloader (GitHub)</a></li>
            </ul>

            <h3>버전</h3>
            <p>현재 버전: <b>{version}</b></p>

            <p style="color:#6b7280;">* 사용자는 콘텐츠 제공자의 약관과 저작권을 준수해야 합니다.</p>
        </body>
        </html>
        """
