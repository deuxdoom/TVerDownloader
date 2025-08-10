# src/ui/main_window_ui.py
# 수정:
# - _create_header: '설정'과 '정보' 버튼 순서 변경
#                   '항상 위' 버튼(on_top_btn)의 텍스트를 핀 아이콘으로 변경하고 관련 로직 단순화

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
    QLabel, QListWidget, QFrame, QSplitter, QTabWidget, QToolButton, QMenu
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from src.icon import get_app_icon

class MainWindowUI:
    """메인 윈도우의 UI 위젯 생성 및 레이아웃 설정을 담당합니다."""

    def __init__(self, main_window):
        self.main_window = main_window
        main_window.setWindowIcon(get_app_icon())
        main_window.resize(1100, 700)

    def setup_ui(self):
        """메인 윈도우의 모든 UI를 구성합니다."""
        central = QWidget()
        self.main_window.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        self._create_header(root)
        self._create_input_bar(root)
        self._create_tabs(root)

    def _create_header(self, root_layout):
        header = QFrame(objectName="AppHeader")
        layout = QHBoxLayout(header); layout.setContentsMargins(16, 10, 16, 10); layout.setSpacing(8)

        self.app_title = QLabel("티버 다운로더 (TVer Downloader)", objectName="AppTitle")
        self.about_button = QPushButton("정보", objectName="PrimaryButton")
        self.settings_button = QPushButton("설정", objectName="PrimaryButton")
        
        # '항상 위' 버튼 아이콘 및 초기 상태 설정
        self.on_top_btn = QToolButton(objectName="OnTopButton", toolTip="항상 위")
        self.on_top_btn.setCheckable(True)
        self.on_top_btn.setFixedSize(28, 28)
        self.on_top_btn.setText("📌") # 아이콘을 핀 모양으로 변경

        layout.addWidget(self.app_title)
        layout.addStretch(1)
        # 버튼 추가 순서 변경: 설정 -> 정보
        layout.addWidget(self.settings_button)
        layout.addWidget(self.about_button)
        layout.addWidget(self.on_top_btn)
        root_layout.addWidget(header)

    def _create_input_bar(self, root_layout):
        input_bar = QFrame(objectName="InputBar")
        layout = QHBoxLayout(input_bar); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText="TVer 영상 URL 붙여넣기", objectName="UrlInput")
        self.bulk_button = QPushButton("다중 추가", objectName="OrangeButton")
        self.add_button = QPushButton("다운로드", objectName="AccentButton")
        layout.addWidget(self.url_input, 1); layout.addWidget(self.bulk_button); layout.addWidget(self.add_button)
        root_layout.addWidget(input_bar)

    def _create_tabs(self, root_layout):
        self.tabs = QTabWidget(objectName="MainTabs")
        self._create_download_tab()
        self._create_history_tab()
        self._create_favorites_tab()
        root_layout.addWidget(self.tabs, 1)

    def _create_download_tab(self):
        tab = QWidget(objectName="DownloadTab"); layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal, objectName="MainSplitter")
        left_pane = QFrame(objectName="LeftPane"); left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(8, 8, 8, 8); row = QHBoxLayout()
        self.queue_label = QLabel("다운로드 목록", objectName="PaneTitle")
        self.queue_count_label = QLabel("0 대기 / 0 진행", objectName="PaneSubtitle")
        row.addWidget(self.queue_label); row.addStretch(1); row.addWidget(self.queue_count_label); left_layout.addLayout(row)
        self.download_list = QListWidget(objectName="DownloadList"); self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.download_list, 1)
        right_pane = QFrame(objectName="RightPane"); right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(8, 8, 8, 8); row = QHBoxLayout()
        self.log_title = QLabel("로그", objectName="PaneTitle")
        self.clear_log_button = QPushButton("지우기", objectName="GhostButton")
        row.addWidget(self.log_title); row.addStretch(1); row.addWidget(self.clear_log_button)
        self.log_output = QTextEdit(objectName="LogOutput", readOnly=True)
        right_layout.addLayout(row); right_layout.addWidget(self.log_output, 1)
        splitter.addWidget(left_pane); splitter.addWidget(right_pane); splitter.setSizes([640, 480])
        layout.addWidget(splitter, 1); self.tabs.addTab(tab, "다운로드")

    def _create_history_tab(self):
        tab = QWidget(objectName="HistoryTab"); layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12); row = QHBoxLayout()
        row.addWidget(QLabel("다운로드 기록", objectName="PaneTitle")); row.addStretch(1)
        self.history_list = QListWidget(objectName="HistoryList"); self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addLayout(row); layout.addWidget(self.history_list, 1); self.tabs.addTab(tab, "기록")

    def _create_favorites_tab(self):
        tab = QWidget(objectName="FavoritesTab")
        layout = QVBoxLayout(tab); layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)
        row = QHBoxLayout(); row.addWidget(QLabel("즐겨찾기 (시리즈)", objectName="PaneTitle")); row.addStretch(1); layout.addLayout(row)
        
        ctrl = QHBoxLayout()
        self.fav_input = QLineEdit(placeholderText="TVer 시리즈 URL (예: https://tver.jp/series/....)")
        self.fav_add_btn = QPushButton("추가", objectName="PrimaryButton")
        self.fav_del_btn = QPushButton("삭제", objectName="DangerButton")
        self.fav_chk_btn = QPushButton("신규 영상 확인", objectName="PurpleButton")
        ctrl.addWidget(self.fav_input, 1)
        ctrl.addWidget(self.fav_add_btn)
        ctrl.addWidget(self.fav_del_btn)
        ctrl.addWidget(self.fav_chk_btn)
        layout.addLayout(ctrl)

        self.fav_list = QListWidget(objectName="FavoritesList"); self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.fav_list, 1); self.tabs.addTab(tab, "즐겨찾기")
    
    def setup_tray(self, app_version):
        tray_icon = self.main_window.tray_icon
        tray_icon.setIcon(get_app_icon())
        tray_icon.setToolTip(f"TVer Downloader {app_version}")
        
        tray_menu = QMenu()
        restore_action = QAction("창 복원", self.main_window, triggered=self.main_window.bring_to_front)
        quit_action = QAction("완전 종료", self.main_window, triggered=self.main_window.quit_application)
        
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        tray_icon.setContextMenu(tray_menu)
        tray_icon.show()