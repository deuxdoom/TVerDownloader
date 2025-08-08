# TVerDownloader.py

import sys
import os
import subprocess
import webbrowser
import json
import re
from datetime import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon,
    QFrame, QSplitter, QTabWidget
)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QCursor, QAction

# ---- 내부 모듈(수정 없음) ----
from src.utils import (
    load_config, save_config, load_history,
    handle_exception, open_file_location,
    open_feedback_link, open_developer_link
)
from src.icon import get_app_icon
from src.themes import ThemeSwitch
from src.widgets import DownloadItemWidget
from src.workers import SetupThread, SeriesParseThread, DownloadThread
from src.dialogs import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.version = "2.0.0"  # 현재 앱 버전(릴리스 태그와 비교)
        self.setWindowTitle("티버 다운로더")
        self.resize(1120, 760)
        self.center()
        self.setAcceptDrops(True)
        self.setWindowIcon(get_app_icon())

        # 상태값
        self.ytdlp_exe_path = ""
        self.ffmpeg_exe_path = ""
        self.task_queue = []
        self.active_downloads = {}
        self.active_urls = set()

        # 기록 로드 + 포맷 감지(리스트/딕셔너리 모두)
        raw_history = load_history()
        self._history_mode = 'dict' if isinstance(raw_history, dict) else 'list'
        self.history = raw_history if raw_history else ([] if self._history_mode == 'list' else {})

        self.config = load_config()
        self.current_theme = self.config.get("theme", "light")
        self.force_quit = False

        # 트레이
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("TVer 다운로더 프로")
        tray_menu = QMenu()
        restore_action = QAction("창 복원", self)
        restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("완전 종료", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

        # UI
        self._build_ui()
        self.apply_stylesheet(self.current_theme)

        # 준비 스레드
        self.setup_thread = SetupThread()
        self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")

        # 최신 버전 체크(메인 단독)
        QTimer.singleShot(300, self.check_update_and_notify)

    # ================== UI ==================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # 헤더
        self.header = QFrame(objectName="AppHeader")
        header_layout = QHBoxLayout(self.header); header_layout.setContentsMargins(16,10,16,10); header_layout.setSpacing(8)
        self.app_title = QLabel("TVer Downloader", objectName="AppTitle")
        self.theme_button = ThemeSwitch(); self.theme_button.toggled.connect(self.toggle_theme)
        self.settings_button = QPushButton("설정", objectName="PrimaryButton"); self.settings_button.clicked.connect(self.open_settings)
        self.feedback_button = QPushButton("버그제보", objectName="LinkButton"); self.feedback_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.feedback_button.clicked.connect(open_feedback_link)
        self.developer_button = QPushButton("개발자 유투브", objectName="LinkButton"); self.developer_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.developer_button.clicked.connect(open_developer_link)
        header_layout.addWidget(self.app_title); header_layout.addStretch(1); header_layout.addWidget(self.developer_button); header_layout.addWidget(self.feedback_button); header_layout.addWidget(self.settings_button); header_layout.addWidget(self.theme_button)

        # 입력바
        self.input_bar = QFrame(objectName="InputBar")
        input_layout = QHBoxLayout(self.input_bar); input_layout.setContentsMargins(16,12,16,12); input_layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText="TVer 에피소드/시리즈 URL 붙여넣기 및 드래그", objectName="UrlInput")
        self.url_input.returnPressed.connect(self.process_input_url)
        self.add_button = QPushButton("다운로드", objectName="AccentButton"); self.add_button.clicked.connect(self.process_input_url)
        input_layout.addWidget(self.url_input, 1); input_layout.addWidget(self.add_button, 0)

        # 탭
        self.tabs = QTabWidget(objectName="MainTabs")

        # [다운로드] 좌: 리스트 / 우: 로그
        self.download_tab = QWidget(objectName="DownloadTab")
        dl_layout = QVBoxLayout(self.download_tab); dl_layout.setContentsMargins(12,12,12,12); dl_layout.setSpacing(8)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, objectName="MainSplitter"); self.splitter.setChildrenCollapsible(False)

        left_frame = QFrame(objectName="LeftPane"); left_layout = QVBoxLayout(left_frame); left_layout.setContentsMargins(8,8,8,8); left_layout.setSpacing(8)
        row = QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.setSpacing(6)
        self.queue_label = QLabel("다운로드 목록", objectName="PaneTitle")
        self.queue_count = QLabel("0 대기 / 0 진행", objectName="PaneSubtitle")
        row.addWidget(self.queue_label); row.addStretch(1); row.addWidget(self.queue_count)
        left_layout.addLayout(row)
        self.download_list = QListWidget(objectName="DownloadList")
        self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_list.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.download_list, 1)

        right_frame = QFrame(objectName="RightPane"); right_layout = QVBoxLayout(right_frame); right_layout.setContentsMargins(8,8,8,8); right_layout.setSpacing(8)
        log_row = QHBoxLayout(); log_row.setContentsMargins(0,0,0,0); log_row.setSpacing(6)
        self.log_title = QLabel("로그", objectName="PaneTitle")
        self.clear_log_button = QPushButton("지우기", objectName="GhostButton")
        self.clear_log_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_log_button.clicked.connect(self.clear_log)  # ✅ 실제 clear
        log_row.addWidget(self.log_title); log_row.addStretch(1); log_row.addWidget(self.clear_log_button)
        right_layout.addLayout(log_row)
        self.log_output = QTextEdit(objectName="LogOutput"); self.log_output.setReadOnly(True); self.log_output.setAcceptRichText(True)
        right_layout.addWidget(self.log_output, 1)

        self.splitter.addWidget(left_frame); self.splitter.addWidget(right_frame); self.splitter.setSizes([640,480])
        dl_layout.addWidget(self.splitter, 1)

        # [기록]
        self.history_tab = QWidget(objectName="HistoryTab")
        his_layout = QVBoxLayout(self.history_tab); his_layout.setContentsMargins(12,12,12,12); his_layout.setSpacing(8)
        top = QHBoxLayout(); top.setContentsMargins(0,0,0,0); top.setSpacing(6)
        self.history_title = QLabel("기록", objectName="PaneTitle")
        self.history_subtitle = QLabel("과거에 다운로드한 항목", objectName="PaneSubtitle")
        top.addWidget(self.history_title); top.addStretch(1); top.addWidget(self.history_subtitle)
        self.history_list = QListWidget(objectName="HistoryList")
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_history_menu)
        his_layout.addLayout(top); his_layout.addWidget(self.history_list, 1)

        self.tabs.addTab(self.download_tab, "다운로드")
        self.tabs.addTab(self.history_tab, "기록")

        root.addWidget(self.header); root.addWidget(self.input_bar); root.addWidget(self.tabs, 1)

        # 상태바 버전
        version_label = QLabel(f"Version: {self.version}"); version_label.setObjectName("VersionLabel")
        self.statusBar().addPermanentWidget(version_label)

        # 입력 비활성(준비 후 활성)
        self.url_input.setEnabled(False); self.add_button.setEnabled(False)

        # 기록 로드 반영
        self.refresh_history_list()

    # ================== 스타일시트(QSS) ==================
    def apply_stylesheet(self, theme: str):
        if theme == "dark":
            qss = """
                QMainWindow { background-color: #101317; }
                QFrame#AppHeader { background-color: #0f1720; border-bottom: 1px solid #1f2833; }
                QFrame#InputBar  { background-color: #121925; border-bottom: 1px solid #1f2833; }
                QSplitter#MainSplitter::handle { background: #0e141f; width: 6px; }
                QTabWidget#MainTabs::pane { border: none; }
                QTabBar::tab { background: #0f1720; color: #9fb5d1; padding: 10px 16px; border: 1px solid #1f2833; border-bottom: none; }
                QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }
                QFrame#LeftPane, QFrame#RightPane, QWidget#HistoryTab { background-color: #0d131c; }
                QLabel#AppTitle { color: #e6edf3; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
                QLabel#PaneTitle { color: #dbe6f3; font-size: 14px; font-weight: 600; }
                QLabel#PaneSubtitle { color: #94a3b8; font-size: 12px; }
                QLineEdit#UrlInput {
                    background: #0b1220; border: 1px solid #233044; border-radius: 8px;
                    padding: 10px 12px; color: #e6edf3; selection-background-color: #1c64f2;
                }
                QLineEdit#UrlInput:focus { border: 1px solid #3b82f6; }
                QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#GhostButton, QPushButton#LinkButton {
                    border-radius: 8px; padding: 8px 14px; font-weight: 600;
                }
                QPushButton#PrimaryButton { background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c; }
                QPushButton#PrimaryButton:hover { background: #263444; }
                QPushButton#AccentButton { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
                QPushButton#AccentButton:hover { background: #1d4ed8; }
                QPushButton#GhostButton { background: transparent; color: #9fb5d1; border: 1px solid #2b3a4c; }
                QPushButton#GhostButton:hover { background: #17202b; }
                QPushButton#LinkButton { background: transparent; color: #80a8ff; border: none; text-decoration: underline; }
                QPushButton#LinkButton:hover { color: #a8c1ff; }
                QLabel { color: #dbe6f3; }
                QListWidget#DownloadList, QListWidget#HistoryList {
                    background: #0d131c; border: 1px solid #1f2833; border-radius: 10px;
                }
                QTextEdit#LogOutput {
                    background: #0b1220; color: #9fb5d1; border: 1px solid #1f2833; border-radius: 10px;
                    font-family: Consolas, "Courier New", monospace; font-size: 12px;
                }
                QProgressBar { border: none; background: #0e1726; height: 12px; border-radius: 6px; text-align: center; color: #e6edf3; }
                QProgressBar::chunk { background-color: #3b82f6; border-radius: 6px; }
                QLabel#VersionLabel { color: #8aa1bd; }

                /* ---- QDialog(설정창 등) 다크 ---- */
                QDialog { background-color: #0d131c; color: #dbe6f3; }
                QDialog QLabel { color: #dbe6f3; }
                QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox {
                    background: #0b1220; color: #e6edf3; border: 1px solid #233044; border-radius: 6px; padding: 6px 8px;
                }
                QDialog QAbstractItemView {
                    background: #0b1220; color: #e6edf3; border: 1px solid #1f2833;
                    selection-background-color: #3b82f6; selection-color: #ffffff;
                }
                QDialog QListWidget {
                    background: #0b1220; border: 1px solid #1f2833; border-radius: 8px;
                }
                QDialog QListWidget::item { color: #e6edf3; }

                /* ✅ 체크박스 텍스트/인디케이터(다크) */
                QDialog QCheckBox { color: #dbe6f3; }
                QDialog QCheckBox::indicator {
                    width: 16px; height: 16px;
                    border: 1px solid #2b3a4c;
                    border-radius: 4px;
                    background: #0b1220;
                }
                QDialog QCheckBox::indicator:hover { border-color: #3a4d66; }
                QDialog QCheckBox::indicator:checked {
                    background: #2563eb;
                    border: 1px solid #1d4ed8;
                }

                QDialog QPushButton {
                    background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c;
                    padding: 6px 12px; border-radius: 6px; min-width: 72px;
                }
                QDialog QPushButton:hover { background: #263444; }
                QDialog QTabWidget::pane { background: #0f1720; border: 1px solid #1f2833; border-radius: 8px; }
                QDialog QTabBar::tab {
                    background: #0f1720; color: #9fb5d1; padding: 8px 12px; border: 1px solid #1f2833; border-bottom: none;
                }
                QDialog QTabBar::tab:selected { background: #0b1220; color: #e6edf3; }

                /* ---- QMessageBox 다크 ---- */
                QMessageBox { background-color: #121925; border: 1px solid #1f2833; }
                QMessageBox QLabel { color: #dbe6f3; }
                QMessageBox QPushButton {
                    background: #1f2a37; color: #e6edf3; border: 1px solid #2b3a4c;
                    padding: 6px 12px; border-radius: 6px; min-width: 72px;
                }
                QMessageBox QPushButton:hover { background: #263444; }
                QMessageBox QPushButton:default { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
            """
        else:
            qss = """
                QMainWindow { background-color: #f6f7fb; }
                QFrame#AppHeader { background-color: #ffffff; border-bottom: 1px solid #e9edf3; }
                QFrame#InputBar  { background-color: #ffffff; border-bottom: 1px solid #e9edf3; }
                QSplitter#MainSplitter::handle { background: #eef1f6; width: 6px; }
                QTabWidget#MainTabs::pane { border: none; }
                QTabBar::tab { background: #ffffff; color: #6b7280; padding: 10px 16px; border: 1px solid #e9edf3; border-bottom: none; }
                QTabBar::tab:selected { background: #f9fafc; color: #111827; }
                QFrame#LeftPane, QFrame#RightPane, QWidget#HistoryTab { background-color: #f9fafc; }
                QLabel#AppTitle { color: #171a21; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
                QLabel#PaneTitle { color: #1f2937; font-size: 14px; font-weight: 600; }
                QLabel#PaneSubtitle { color: #6b7280; font-size: 12px; }
                QLineEdit#UrlInput {
                    background: #ffffff; border: 1px solid #dbe2ea; border-radius: 8px;
                    padding: 10px 12px; color: #111827; selection-background-color: #2563eb;
                }
                QLineEdit#UrlInput:focus { border: 1px solid #2563eb; }
                QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#GhostButton, QPushButton#LinkButton {
                    border-radius: 8px; padding: 8px 14px; font-weight: 600;
                }
                QPushButton#PrimaryButton { background: #eef2f7; color: #111827; border: 1px solid #e3e8ef; }
                QPushButton#PrimaryButton:hover { background: #e4e9f1; }
                QPushButton#AccentButton { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
                QPushButton#AccentButton:hover { background: #1d4ed8; }
                QPushButton#GhostButton { background: transparent; color: #374151; border: 1px solid #e3e8ef; }
                QPushButton#GhostButton:hover { background: #eef2f7; }
                QPushButton#LinkButton { background: transparent; color: #1d4ed8; border: none; text-decoration: underline; }
                QPushButton#LinkButton:hover { color: #153eaf; }
                QLabel { color: #1f2937; }

                /* 리스트 컨테이너(바탕) */
                QListWidget#DownloadList, QListWidget#HistoryList {
                    background: #ffffff; border: 1px solid #e9edf3; border-radius: 10px;
                }
                /* 라이트 테마 항목 텍스트/선택/호버 강제 */
                QListWidget#DownloadList::item, QListWidget#HistoryList::item {
                    color: #111827; padding: 6px 8px;
                }
                QListWidget#DownloadList::item:selected, QListWidget#HistoryList::item:selected {
                    background: #e8efff; color: #0b1742;
                }
                QListWidget#DownloadList::item:hover, QListWidget#HistoryList::item:hover {
                    background: #f2f6ff;
                }

                QTextEdit#LogOutput {
                    background: #ffffff; color: #334155; border: 1px solid #e9edf3; border-radius: 10px;
                    font-family: Consolas, "Courier New", monospace; font-size: 12px;
                }
                QProgressBar { border: none; background: #eef2f7; height: 12px; border-radius: 6px; text-align: center; color: #111827; }
                QProgressBar::chunk { background-color: #2563eb; border-radius: 6px; }
                QLabel#VersionLabel { color: #6b7280; }

                /* ---- QDialog(설정창 등) 라이트 ---- */
                QDialog { background-color: #ffffff; color: #111827; }
                QDialog QLabel { color: #1f2937; }
                QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox {
                    background: #ffffff; color: #111827; border: 1px solid #dbe2ea; border-radius: 6px; padding: 6px 8px;
                }
                QDialog QAbstractItemView {
                    background: #ffffff; color: #111827; border: 1px solid #e3e8ef;
                    selection-background-color: #2563eb; selection-color: #ffffff;
                }
                QDialog QListWidget {
                    background: #ffffff; border: 1px solid #e9edf3; border-radius: 8px;
                }
                QDialog QListWidget::item { color: #111827; }

                /* ✅ 체크박스 텍스트/인디케이터(라이트) */
                QDialog QCheckBox { color: #111827; }
                QDialog QCheckBox::indicator {
                    width: 16px; height: 16px;
                    border: 1px solid #cfd8e3;
                    border-radius: 4px;
                    background: #ffffff;
                }
                QDialog QCheckBox::indicator:hover { border-color: #9db2cc; }
                QDialog QCheckBox::indicator:unchecked { background: #ffffff; }
                QDialog QCheckBox::indicator:checked {
                    background: #2563eb;
                    border: 1px solid #1d4ed8;
                }
                QDialog QCheckBox::indicator:disabled {
                    background: #f3f4f6; border-color: #e5e7eb;
                }

                QDialog QPushButton {
                    background: #eef2f7; color: #111827; border: 1px solid #e3e8ef;
                    padding: 6px 12px; border-radius: 6px; min-width: 72px;
                }
                QDialog QPushButton:hover { background: #e4e9f1; }
                QDialog QTabWidget::pane { background: #ffffff; border: 1px solid #e9edf3; border-radius: 8px; }
                QDialog QTabBar::tab {
                    background: #ffffff; color: #6b7280; padding: 8px 12px; border: 1px solid #e9edf3; border-bottom: none;
                }
                QDialog QTabBar::tab:selected { background: #f9fafc; color: #111827; }

                /* ---- QMessageBox 라이트 ---- */
                QMessageBox { background-color: #ffffff; border: 1px solid #e9edf3; }
                QMessageBox QLabel { color: #111827; }
                QMessageBox QPushButton {
                    background: #eef2f7; color: #111827; border: 1px solid #e3e8ef;
                    padding: 6px 12px; border-radius: 6px; min-width: 72px;
                }
                QMessageBox QPushButton:hover { background: #e4e9f1; }
                QMessageBox QPushButton:default { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }
            """
        self.setStyleSheet(qss)
        if hasattr(self, "theme_button"):
            self.theme_button.update_theme(theme)

    # ================== 테마 토글 ==================
    def toggle_theme(self, is_dark: bool):
        self.current_theme = "dark" if is_dark else "light"
        self.config["theme"] = self.current_theme
        save_config(self.config)
        self.apply_stylesheet(self.current_theme)
        if hasattr(self, 'theme_button'):
            self.theme_button.setChecked(is_dark)
            self.theme_button.update_theme(self.current_theme)

    # ================== 트레이/종료 ==================
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.append_log("트레이 아이콘 더블클릭으로 창 복원됨.")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray_icon.showMessage("TVer 다운로더", "프로그램이 트레이로 이동했습니다.", get_app_icon(), 2000)
            event.accept()

    def closeEvent(self, event):
        if self.force_quit:
            for url in list(self.active_downloads.keys()):
                self.stop_download(url)
            event.accept(); return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('종료 확인')
        msg_box.setText("종료하시겠습니까?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_button = msg_box.addButton("예", QMessageBox.ButtonRole.YesRole)
        no_button = msg_box.addButton("아니오", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_button)
        msg_box.exec()
        if msg_box.clickedButton() == yes_button:
            if self.active_downloads:
                for url in list(self.active_downloads.keys()):
                    self.stop_download(url)
            self.force_quit = True
            self.quit_application()
            event.accept()
        else:
            event.ignore()

    def quit_application(self):
        self.append_log("프로그램이 완전히 종료됩니다.")
        self.force_quit = True
        for url in list(self.active_downloads.keys()):
            self.stop_download(url)
        QApplication.quit()

    # ================== 유틸 ==================
    def center(self):
        qr = self.frameGeometry(); cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp); self.move(qr.topLeft())

    def append_log(self, text: str):
        if "[오류]" in text or "[치명적 오류]" in text:
            self.log_output.append(f'<span style="color: #e57373;">{text}</span>')
        elif "완료" in text or "성공" in text:
            self.log_output.append(f'<span style="color: #4caf50;">{text}</span>')
        else:
            self.log_output.append(text)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def clear_log(self):
        """로그 창 실제 지우기"""
        self.log_output.clear()

    # ================== 준비 완료 콜백 ==================
    def on_setup_finished(self, success: bool, ytdlp_exe_path: str, ffmpeg_exe_path: str):
        if success:
            self.ytdlp_exe_path = ytdlp_exe_path
            self.ffmpeg_exe_path = ffmpeg_exe_path
            self.append_log("=" * 65)
            self.append_log("📢 [안내] TVer는 일본 지역 제한이 있습니다.")
            self.append_log("📢 원활한 다운로드를 위해 반드시 일본 VPN을 켜고 사용해주세요.")
            self.append_log("=" * 65)
            self.append_log("\n환경 설정 완료. 다운로드를 시작할 수 있습니다.")
            self.url_input.setEnabled(True)
            self.add_button.setEnabled(True)
            self.theme_button.setChecked(self.current_theme == "dark")
        else:
            self.append_log("=" * 65 + "\n[치명적 오류] 환경 설정 실패. 로그를 확인하고 재시작하세요.")
            QMessageBox.critical(self, "환경 설정 실패",
                                 "yt-dlp 또는 ffmpeg를 다운로드하지 못했습니다.\n인터넷 연결을 확인하고 다시 시도하세요.")

    # ================== 설정/폴더 ==================
    def get_download_folder(self) -> Optional[str]:
        return self.config.get("download_folder", "")

    def select_folder(self) -> Optional[str]:
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.get_download_folder() or "")
        if folder:
            self.config["download_folder"] = folder; save_config(self.config)
            self.append_log(f"다운로드 폴더가 '{folder}'로 설정되었습니다.")
            return folder
        return None

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = load_config()
            self.apply_stylesheet(self.current_theme)
            self.append_log("설정이 저장되었습니다.")

    # ================== URL 처리 ==================
    def process_input_url(self):
        url = self.url_input.text().strip()
        if not url: return
        if "/series/" in url:
            self.series_parse_thread = SeriesParseThread(url, self.ytdlp_exe_path)
            self.series_parse_thread.log.connect(self.append_log)
            self.series_parse_thread.finished.connect(self.on_series_parsed)
            self.series_parse_thread.start()
            self.url_input.setEnabled(False); self.add_button.setEnabled(False)
        else:
            self.add_url_to_queue(url)
        self.url_input.clear()

    def on_series_parsed(self, episode_urls: List[str]):
        self.url_input.setEnabled(True); self.add_button.setEnabled(True)
        for url in episode_urls:
            self.add_url_to_queue(url)

    # ================== 다운로드 큐 ==================
    def add_url_to_queue(self, url: str):
        if not url: return
        if url in self.active_urls:
            self.append_log(f"[알림] 이미 대기열/다운로드 중: {url}"); return

        # 기록 중복 체크
        if self._history_has_url(url):
            title_preview = self._history_get_title(url)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle('중복 다운로드')
            msg_box.setText(f"이 항목은 이미 다운로드한 기록이 있습니다:\n\n{title_preview}\n\n다시 다운로드하시겠습니까?")
            yes_button = msg_box.addButton("예", QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton("아니오", QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(no_button)
            msg_box.exec()
            if msg_box.clickedButton() == no_button:
                self.append_log(f"[알림] 중복 다운로드 취소: {url}")
                return

        self.active_urls.add(url)
        item = QListWidgetItem()
        widget = DownloadItemWidget(url)
        widget.stop_requested.connect(self.stop_download)
        widget.play_requested.connect(self.play_file)
        item.setSizeHint(widget.sizeHint())
        self.download_list.insertItem(0, item)
        self.download_list.setItemWidget(item, widget)
        self.task_queue.append({'item': item, 'widget': widget, 'url': url})

        self._update_queue_counter()
        self.check_queue_and_start()

    def check_queue_and_start(self):
        while len(self.active_downloads) < self.config.get("max_concurrent_downloads", 3) and self.task_queue:
            task = self.task_queue.pop(0)
            url = task['url']
            download_folder = self.get_download_folder()
            if not download_folder:
                self.append_log("다운로드 폴더가 지정되지 않았습니다. 선택창을 엽니다...")
                download_folder = self.select_folder()
                if not download_folder:
                    self.append_log(f"'{task['widget'].title_label.text()}' 취소됨(폴더 미선택)")
                    self.download_list.takeItem(self.download_list.row(task['item']))
                    self.active_urls.remove(url); self._update_queue_counter(); continue

            parts = self.config.get("filename_parts", {})
            order = self.config.get("filename_order", ["series", "upload_date", "episode_number", "episode", "id"])
            filename_format = " - ".join(f"%({key})s" for key in order if parts.get(key, False) and key != 'id')
            if parts.get("id", False): filename_format += " [%(id)s]"
            filename_format += ".mp4"
            quality_format = self.config.get("quality", "bv*+ba/b")

            thread = DownloadThread(url, download_folder, self.ytdlp_exe_path, self.ffmpeg_exe_path, filename_format, quality_format)
            thread.progress.connect(self.update_download_progress)
            thread.finished.connect(self.on_download_finished)
            self.active_downloads[url] = {'thread': thread, 'widget': task['widget'], 'item': task['item']}
            thread.start()

        self._update_queue_counter()

    def _update_queue_counter(self):
        self.queue_count.setText(f"{len(self.task_queue)} 대기 / {len(self.active_downloads)} 진행")

    # ================== 진행/완료 ==================
    def update_download_progress(self, url: str, data: dict):
        if url in self.active_downloads:
            self.active_downloads[url]['widget'].update_progress(data)
        if 'log' in data and data['log']:
            self.append_log(data['log'])

    def on_download_finished(self, url: str, success: bool):
        if url in self.active_downloads:
            widget = self.active_downloads[url]['widget']; title = widget.title_label.text()
            if success:
                self.append_log(f"--- '{title}' 다운로드 성공 ---")
                self._history_add(url, title); self.refresh_history_list()
            else:
                self.append_log(f"--- '{title}' 다운로드 실패 ---")
            del self.active_downloads[url]
            if url in self.active_urls: self.active_urls.remove(url)

        self.check_queue_and_start()
        if not self.active_downloads and not self.task_queue:
            self.on_all_downloads_finished()

    def on_all_downloads_finished(self):
        self.append_log("모든 다운로드가 완료되었습니다.")
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage("다운로드 완료", "모든 작업이 끝났습니다!", get_app_icon(), 5000)
        else:
            QMessageBox.information(self, "다운로드 완료", "모든 작업이 끝났습니다!")
        post_action = self.config.get("post_action", "None")
        if post_action == "Open Folder":
            try: os.startfile(self.get_download_folder() or "")
            except Exception as e: self.append_log(f"[오류] 폴더 열기 실패: {e}")
        elif post_action == "Shutdown":
            try: subprocess.run(["shutdown", "/s", "/t", "60"])
            except Exception as e: self.append_log(f"[오류] 시스템 종료 명령 실패: {e}")
        self._update_queue_counter()

    # ================== 컨텍스트 메뉴 ==================
    def stop_download(self, url: str):
        if url in self.active_downloads:
            self.append_log(f"'{self.active_downloads[url]['widget'].title_label.text()}' 다운로드 중단...")
            self.active_downloads[url]['thread'].stop()

    def play_file(self, filepath: str):
        try:
            os.startfile(filepath); self.append_log(f"영상 재생: {filepath}")
        except Exception as e:
            self.append_log(f"[오류] 영상 재생 실패: {e}")
            QMessageBox.critical(self, "재생 오류", f"영상 파일을 재생하지 못했습니다: {e}")

    def show_context_menu(self, pos):
        item = self.download_list.itemAt(pos)
        if not item: return
        widget = self.download_list.itemWidget(item); url = widget.url; status = widget.status
        menu = QMenu()
        if status == '완료' and widget.final_filepath and os.path.exists(widget.final_filepath):
            a1 = QAction("파일 위치 열기", self); a1.triggered.connect(lambda: open_file_location(widget.final_filepath)); menu.addAction(a1)
            a2 = QAction("영상 재생", self); a2.triggered.connect(lambda: self.play_file(widget.final_filepath)); menu.addAction(a2); menu.addSeparator()
        if status not in ['다운로드 중', '정보 분석 중...', '후처리 중...']:
            rm = QAction("목록에서 제거", self); rm.triggered.connect(lambda: self.remove_item(item, url)); menu.addAction(rm)
        if menu.actions(): menu.exec(self.download_list.mapToGlobal(pos))

    def remove_item(self, item, url):
        row = self.download_list.row(item); self.download_list.takeItem(row)
        self.task_queue = [t for t in self.task_queue if t['url'] != url]
        if url in self.active_urls: self.active_urls.remove(url)
        self._update_queue_counter()

    # ================== 기록 탭(포맷 호환) ==================
    def refresh_history_list(self):
        self.history_list.clear()
        if self._history_mode == 'list':
            items = sorted([e for e in self.history if isinstance(e, dict)],
                           key=lambda e: e.get("date", ""), reverse=True)
            for e in items:
                url = e.get("url", ""); title = e.get("title", "(제목 없음)"); date = e.get("date", "")
                text = f"{title}  •  {date}\n{url}"
                item = QListWidgetItem(text); item.setData(Qt.ItemDataRole.UserRole, url)
                self.history_list.addItem(item)
        else:
            items = sorted(self.history.items(), key=lambda kv: kv[1].get("date", ""), reverse=True)
            for url, meta in items:
                title = meta.get("title", "(제목 없음)"); date = meta.get("date", "")
                text = f"{title}  •  {date}\n{url}"
                item = QListWidgetItem(text); item.setData(Qt.ItemDataRole.UserRole, url)
                self.history_list.addItem(item)

    def show_history_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu()
        redl = QAction("다시 다운로드", self); redl.triggered.connect(lambda: self.add_url_to_queue(url)); menu.addAction(redl)
        rm = QAction("기록에서 제거", self); rm.triggered.connect(lambda: self.remove_from_history(url)); menu.addAction(rm)
        menu.exec(self.history_list.mapToGlobal(pos))

    def remove_from_history(self, url: str):
        self._history_remove(url); self.refresh_history_list()
        self.append_log(f"[알림] 기록에서 제거됨: {url}")

    # ---- 기록 헬퍼 ----
    def _history_has_url(self, url: str) -> bool:
        if self._history_mode == 'list':
            return any(isinstance(e, dict) and e.get("url") == url for e in self.history)
        return url in self.history

    def _history_get_title(self, url: str) -> str:
        if self._history_mode == 'list':
            for e in self.history:
                if isinstance(e, dict) and e.get("url") == url:
                    return e.get("title", "(제목 없음)")
            return "(제목 없음)"
        return self.history.get(url, {}).get("title", "(제목 없음)")

    def _history_add(self, url: str, title: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self._history_mode == 'list':
            self.history = [e for e in self.history if not (isinstance(e, dict) and e.get("url") == url)]
            self.history.insert(0, {"url": url, "title": title, "date": now})
        else:
            self.history[url] = {"title": title, "date": now}
        self._history_save()

    def _history_remove(self, url: str):
        if self._history_mode == 'list':
            self.history = [e for e in self.history if not (isinstance(e, dict) and e.get("url") == url)]
        else:
            self.history.pop(url, None)
        self._history_save()

    def _history_save(self):
        try:
            with open("urlhistory.json", "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.append_log(f"[오류] 기록 저장 실패: {e}")

    # ================== 최신 버전 체크(메인 단독) ==================
    def check_update_and_notify(self):
        try:
            import requests
        except Exception:
            self.append_log("[업데이트] requests 미설치. 확인 건너뜀(pip install requests).")
            return

        API = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
        PAGE = "https://github.com/deuxdoom/TVerDownloader/releases/latest"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "TVerDownloader (update-check)"}

        def norm(tag: str) -> tuple:
            if not tag: return (0,0,0)
            t = tag.strip()
            if t.startswith(("v","V")): t = t[1:]
            t = t.split('-',1)[0].split('+',1)[0]
            nums = re.findall(r'\d+', t)[:3]
            parts = [int(x) for x in nums] + [0]*(3-len(nums))
            return tuple(parts[:3])

        def newer(cur: str, latest: str) -> bool:
            return norm(latest) > norm(cur)

        # API 시도
        try:
            r = requests.get(API, headers=headers, timeout=10); r.raise_for_status()
            js = r.json()
            latest_tag = js.get("tag_name") or js.get("name") or ""
            html_url = js.get("html_url") or PAGE
            body = js.get("body") or ""
            if newer(self.version, latest_tag):
                self._show_update_prompt(latest_tag, html_url, body)
            return
        except Exception as api_err:
            # HTML 폴백
            try:
                r = requests.get(PAGE, headers=headers, timeout=10); r.raise_for_status()
                m = re.search(r'>\s*v?(\d+\.\d+\.\d+)\s*<', r.text)
                latest_tag = f"v{m.group(1)}" if m else ""
                if latest_tag and newer(self.version, latest_tag):
                    self._show_update_prompt(latest_tag, PAGE, "")
            except Exception as html_err:
                self.append_log(f"[업데이트] 확인 실패: api:{api_err} / html:{html_err}")

    def _show_update_prompt(self, latest_tag: str, url: str, body: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("새 버전 확인")
        text = f"새 버전 {latest_tag} 이(가) 공개되었습니다.\n지금 릴리스 페이지로 이동할까요?"
        if body:
            preview = body.strip().splitlines()[0][:140]
            if preview:
                text += f"\n\n- 릴리스 노트: {preview}"
        msg.setText(text)
        go_btn = msg.addButton("이동", QMessageBox.ButtonRole.AcceptRole)
        later_btn = msg.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(go_btn)
        msg.exec()
        if msg.clickedButton() == go_btn:
            try: webbrowser.open(url or "https://github.com/deuxdoom/TVerDownloader/releases/latest")
            except Exception as e: self.append_log(f"[업데이트] 브라우저 열기 실패: {e}")


# ================== 엔트리포인트 ==================
if __name__ == "__main__":
    sys.excepthook = handle_exception
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r')
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
