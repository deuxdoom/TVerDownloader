import sys
import os
import subprocess  # subprocess 임포트 추가
import requests
import json
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTextEdit, QLabel, QListWidget,
                             QListWidgetItem, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon, QTabWidget)
from PyQt6.QtCore import Qt, QEvent, QUrl, QSize  # QSize 임포트
from PyQt6.QtGui import QCursor, QAction, QIcon, QDesktopServices
from src.utils import load_config, save_config, load_history, add_to_history, remove_from_history, get_startupinfo, open_file_location, handle_exception, get_app_icon, open_feedback_link, open_developer_link
from src.themes import ThemeSwitch  # ThemeSwitch만 임포트
from src.widgets import DownloadItemWidget
from src.workers import SetupThread, SeriesParseThread, DownloadThread
from src.dialogs import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.version = "1.2.3"  # 버전 유지
        self.setWindowTitle("TVer 다운로더")
        self.resize(800, 700)
        self.center()
        self.setAcceptDrops(True)
        self.setWindowIcon(get_app_icon())
        self.ytdlp_exe_path = ""
        self.ffmpeg_exe_path = ""
        self.task_queue = []
        self.active_downloads = {}
        self.active_urls = set()
        self.history = load_history()  # 리스트로 반환, 기존 딕셔너리 호환
        self.config = load_config()
        self.current_theme = self.config.get("theme", "light")
        self.force_quit = False  # 완전 종료 플래그 추가
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
        # UI 설정을 메인 파일로 복원
        self.setup_ui()
        self.apply_stylesheet(self.current_theme)  # 스타일시트 적용 로직 복원
        self.setup_thread = SetupThread()
        self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")
        # 버전 체크 추가
        self.check_for_updates()

    def setup_ui(self):
        # UI 설정을 QTabWidget로 수정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 탭 위젯 추가
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 다운로드 탭
        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)
        download_layout.setContentsMargins(0, 0, 0, 0)
        download_layout.setSpacing(0)

        input_container = QWidget()
        input_container.setObjectName("inputContainer")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(15, 10, 15, 10)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("다운로드할 TVer URL을 여기에 붙여넣거나 드래그하세요")
        self.url_input.returnPressed.connect(self.process_input_url)
        self.add_button = QPushButton("다운로드")
        self.settings_button = QPushButton("설정")
        self.theme_button = ThemeSwitch()
        input_layout.addWidget(self.url_input, 1)
        input_layout.addWidget(self.add_button)
        input_layout.addWidget(self.settings_button)
        input_layout.addWidget(self.theme_button)
        download_layout.addWidget(input_container)

        self.download_list = QListWidget()
        self.download_list.setAlternatingRowColors(True)
        self.download_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_list.customContextMenuRequested.connect(self.show_download_context_menu)
        download_layout.addWidget(self.download_list, 1)

        log_container = QWidget()
        log_container.setObjectName("logContainer")
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 5, 0, 0)
        log_layout.setSpacing(5)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setAcceptRichText(True)
        self.log_output.setObjectName("logOutput")
        log_button_layout = QHBoxLayout()
        log_button_layout.setContentsMargins(15, 0, 15, 5)
        self.clear_log_button = QPushButton("로그 지우기")
        self.clear_log_button.setObjectName("clearLogButton")
        log_button_layout.addWidget(self.clear_log_button)
        log_button_layout.addStretch(1)
        log_layout.addWidget(self.log_output, 1)
        log_layout.addLayout(log_button_layout)
        download_layout.addWidget(log_container)

        self.clear_log_button.clicked.connect(lambda: self.append_log("로그 내역이 삭제되었습니다."))
        self.add_button.clicked.connect(self.process_input_url)
        self.settings_button.clicked.connect(self.open_settings)
        self.theme_button.toggled.connect(self.toggle_theme)
        self.url_input.setEnabled(False)
        self.add_button.setEnabled(False)
        self.tab_widget.addTab(download_tab, "다운로드")

        # 기록 탭
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        self.history_list = QListWidget()
        self.history_list.setAlternatingRowColors(True)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        self.history_list.setSpacing(5)  # 노트 줄 간격 수준 (5px)
        self._load_history_items()
        history_layout.addWidget(self.history_list)
        self.tab_widget.addTab(history_tab, "기록")

        status_bar = self.statusBar()
        self.developer_label = QPushButton("개발자 : 사시코")
        self.developer_label.setObjectName("statusBarButton")
        self.developer_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.developer_label.clicked.connect(open_developer_link)
        version_label = QLabel(f"Version: {self.version}")
        self.feedback_button = QPushButton("버그제보")
        self.feedback_button.setObjectName("statusBarButton")
        self.feedback_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.feedback_button.clicked.connect(open_feedback_link)
        status_bar.addPermanentWidget(self.developer_label)
        status_bar.addPermanentWidget(QLabel(" | "))
        status_bar.addPermanentWidget(version_label)
        status_bar.addPermanentWidget(QLabel(" | "))
        status_bar.addPermanentWidget(self.feedback_button)

    def _load_history_items(self):
        self.history = load_history()  # 리스트로 반환, 기존 딕셔너리 호환
        self.history_list.clear()
        for index, entry in enumerate(self.history, 1):  # 1부터 번호 시작
            date = entry.get("date", "날짜 없음")
            item_text = f"{index}. {entry.get('title', '제목 없음')} - {date}"
            item = QListWidgetItem(item_text)
            item.setSizeHint(QSize(0, 20))  # 항목 높이 조정 (노트 줄 간격에 맞춤)
            self.history_list.addItem(item)

    def show_download_context_menu(self, pos):
        item = self.download_list.itemAt(pos)
        if not item:
            return
        widget = self.download_list.itemWidget(item)
        url = widget.url
        status = widget.status
        menu = QMenu()
        if status == '완료' and widget.final_filepath and os.path.exists(widget.final_filepath):
            open_folder_action = QAction("파일 위치 열기", self)
            open_folder_action.triggered.connect(lambda: open_file_location(widget.final_filepath))
            menu.addAction(open_folder_action)
            play_action = QAction("영상 재생", self)
            play_action.triggered.connect(lambda: self.play_file(widget.final_filepath))
            menu.addAction(play_action)
            menu.addSeparator()
        if status not in ['다운로드 중', '정보 분석 중...', '후처리 중...']:
            remove_action = QAction("목록에서 제거", self)
            remove_action.triggered.connect(lambda: self.remove_item(item, url))
            menu.addAction(remove_action)
        if menu.actions():
            menu.exec(self.download_list.mapToGlobal(pos))

    def show_history_context_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if not item:
            return
        title_date = item.text().split(" - ")
        if len(title_date) < 2:
            return
        title = title_date[0].split(". ", 1)[1] if ". " in title_date[0] else title_date[0]
        url = next((entry["url"] for entry in self.history if entry.get("title") == title), None)
        if not url:
            return
        menu = QMenu()
        remove_action = QAction("기록 삭제", self)
        remove_action.triggered.connect(lambda: self.remove_history_item(item, url))
        redownload_action = QAction("다시 다운로드", self)
        redownload_action.triggered.connect(lambda: self.requeue_item(url))
        menu.addAction(remove_action)
        menu.addAction(redownload_action)
        if menu.actions():
            menu.exec(self.history_list.mapToGlobal(pos))

    def remove_history_item(self, item, url):
        if remove_from_history(url):
            self.history_list.takeItem(self.history_list.row(item))
            self.history = [entry for entry in self.history if entry["url"] != url]
            self._load_history_items()  # 번호 재정렬 위해 갱신
            self.append_log(f"기록 삭제: {url}")
        else:
            self.append_log(f"[오류] 기록 삭제 실패: {url}")

    def requeue_item(self, url):
        self.add_url_to_queue(url)
        self.append_log(f"다시 다운로드 예약: {url}")

    def apply_stylesheet(self, theme):
        # apply_stylesheet 로직을 TVerDownloader로 복원
        if theme == 'dark':
            stylesheet = """
                QMainWindow, QDialog { background-color: #1e2128; }
                QStatusBar { color: #8f9aa6; font-size: 11px; } QStatusBar::item { border: 0px; }
                QPushButton#statusBarButton { background-color: transparent; color: #62a0ea; padding: 0px 5px; font-size: 11px; text-decoration: underline; }
                QPushButton#statusBarButton:hover { color: #82baff; }
                QWidget#inputContainer { background-color: #2c313c; border-bottom: 1px solid #1e2128; }
                QLineEdit, QSpinBox { background-color: #2c313c; border: 1px solid #4f5b6e; border-radius: 4px;
                            padding: 8px; color: #d0d0d0; font-size: 14px; }
                QLineEdit:focus, QSpinBox:focus { border: 1px solid #62a0ea; }
                QPushButton { background-color: #4f5b6e; color: #d0d0d0; border: none;
                              border-radius: 4px; padding: 8px 16px; font-size: 14px; }
                QPushButton:hover { background-color: #62a0ea; }
                QPushButton:pressed { background-color: #5290da; }
                QPushButton#stopButton { font-size: 16px; font-weight: bold; padding: 0px; padding-bottom: 2px; }
                QPushButton#stopButton:hover { background-color: #e57373; color: #ffffff; }
                QListWidget { background-color: #1e2128; border: none; color: #d0d0d0; }
                QListWidget::item { border-bottom: 1px solid #2c313c; padding: 2px 0; }  /* 간격 조정 */
                QListWidget::item:alternate { background-color: #23272e; }
                QWidget#logContainer { background-color: #1a1d23; border-top: 1px solid #2c313c; }
                QTextEdit#logOutput { background-color: #1a1d23; border: none;
                                      color: #8f9aa6; font-family: Consolas, Courier New, monospace; }
                QPushButton#clearLogButton { font-size: 11px; padding: 4px 10px; max-width: 80px; }
                QLabel { color: #d0d0d0; }
                QProgressBar { border: none; border-radius: 6px; background-color: #2c313c; text-align: center; }
                QProgressBar::chunk { background-color: #62a0ea; border-radius: 6px; animation: progress 1s linear infinite; }
                QTabWidget::pane { border: 1px solid #4f5b6e; }
                QTabBar::tab { background: #2c313c; color: #d0d0d0; padding: 8px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background: #1e2128; }
                QCheckBox { color: #ffffff; background-color: #2c313c; } # 텍스트 색상 밝게 조정 (시인성 향상)
                QCheckBox::indicator { width: 18px; height: 18px; } # 크기 증가 (시인성 향상)
                QCheckBox::indicator:unchecked { background-color: #333a4d; border: 2px solid #6b7280; } # 배경 더 어두운 색으로, 테두리 두께 증가
                QCheckBox::indicator:checked { background-color: #4caf50; border: 2px solid #4caf50; } # 체크된 상태 색상 변경, 테두리 두께 증가
                QCheckBox::indicator:checked::after { content: '✓'; color: #ffffff; font-size: 14px; font-weight: bold; } # 체크 표시 밝은 색으로, 크기 증가
                QComboBox { background-color: #2c2f3a; color: #e0e0e0; border: 1px solid #4f5b6e; border-radius: 4px; padding: 4px; }
                QComboBox::drop-down { border: none; }
                QComboBox QAbstractItemView { background-color: #2c313c; color: #d0d0d0; border: 1px solid #4f5b6e; selection-background-color: #62a0ea; }
                @keyframes progress { from { background-position: 0px; } to { background-position: 40px; } }
            """
        else:
            stylesheet = """
                QMainWindow, QDialog { background-color: #f0f2f5; }
                QStatusBar { color: #555; font-size: 11px; } QStatusBar::item { border: 0px; }
                QPushButton#statusBarButton { background-color: transparent; color: #0078d4; padding: 0px 5px; border: none; font-size: 11px; text-decoration: underline; }
                QPushButton#statusBarButton:hover { color: #005a9e; }
                QWidget#inputContainer { background-color: #ffffff; border-bottom: 1px solid #dcdcdc; }
                QLineEdit, QSpinBox { background-color: #ffffff; border: 1px solid #dcdcdc; border-radius: 4px;
                            padding: 8px; color: #212121; font-size: 14px; }
                QLineEdit:focus, QSpinBox:focus { border: 1px solid #0078d4; }
                QPushButton { background-color: #e1e1e1; color: #212121; border: 1px solid #dcdcdc;
                              border-radius: 4px; padding: 8px 16px; font-size: 14px; }
                QPushButton:hover { background-color: #d1d1d1; }
                QPushButton:pressed { background-color: #c1c1c1; }
                QPushButton#stopButton { font-size: 16px; font-weight: bold; padding: 0px; padding-bottom: 2px; }
                QPushButton#stopButton:hover { background-color: #e57373; color: #ffffff; border: 1px solid #d32f2f; }
                QListWidget { background-color: #f0f2f5; border: none; color: #212121; }
                QListWidget::item { border-bottom: 1px solid #e0e0e0; padding: 2px 0; }  /* 간격 조정 */
                QListWidget::item:alternate { background-color: #ffffff; }
                QWidget#logContainer { background-color: #ffffff; border-top: 1px solid #dcdcdc; }
                QTextEdit#logOutput { background-color: #ffffff; border: none;
                                      color: #444; font-family: Consolas, Courier New, monospace; }
                QPushButton#clearLogButton { font-size: 11px; padding: 4px 10px; max-width: 80px; }
                QLabel { color: #212121; }
                QProgressBar { border: none; border-radius: 6px; background-color: #e0e0e0; text-align: center; }
                QProgressBar::chunk { background-color: #0078d4; border-radius: 6px; animation: progress 1s linear infinite; }
                QTabWidget::pane { border: 1px solid #dcdcdc; }
                QTabBar::tab { background: #e1e1e1; color: #212121; padding: 8px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background: #f0f2f5; }
                QCheckBox { color: #000000; } # 텍스트 색상 검정 유지
                QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #808080; } # 테두리 두께 증가, 회색으로 조정
                QCheckBox::indicator:unchecked { background-color: #f0f0f0; } # 체크되지 않은 배경 연한 회색으로 (시인성 향상)
                QCheckBox::indicator:checked { background-color: #ffffff; } # 체크된 배경 흰색 유지
                QCheckBox::indicator:checked::after { content: '✓'; color: #4caf50; font-size: 14px; font-weight: bold; } # 체크 표시 녹색으로 변경, 크기 증가 (시인성 향상)
                QComboBox { background-color: #f0f2f5; color: #333333; border: 1px solid #dcdcdc; border-radius: 4px; padding: 4px; }
                QComboBox::drop-down { border: none; }
                QComboBox QAbstractItemView { background-color: #ffffff; color: #212121; border: 1px solid #dcdcdc; selection-background-color: #0078d4; } # 드롭다운 배경 하얀색으로 수정
                @keyframes progress { from { background-position: 0px; } to { background-position: 40px; } }
            """
        self.setStyleSheet(stylesheet)
        if hasattr(self, 'theme_button'):
            self.theme_button.update_theme(theme)

    def toggle_theme(self, is_dark):
        # 토글 메서드
        self.current_theme = "dark" if is_dark else "light"
        self.config["theme"] = self.current_theme
        save_config(self.config)
        self.apply_stylesheet(self.current_theme)
        if hasattr(self, 'theme_button'):
            self.theme_button.setChecked(is_dark)
            self.theme_button.update_theme(self.current_theme)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.append_log("트레이 아이콘 더블클릭으로 창 복원됨.")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray_icon.showMessage("TVer 다운로더", "프로그램이 트레이로 이동했습니다.", QIcon(get_app_icon()), 2000)
            event.accept()

    def closeEvent(self, event):
        if self.force_quit:  # 완전 종료 요청 시 즉시 종료
            for url in list(self.active_downloads.keys()):
                self.stop_download(url)
            event.accept()
            return
        # 다운로드 상태와 상관없이 "종료하시겠습니까?" 팝업 표시 (사용자 요청 반영)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('종료 확인')
        msg_box.setText("종료하시겠습니까?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_button = msg_box.addButton("예", QMessageBox.ButtonRole.YesRole)
        no_button = msg_box.addButton("아니오", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(no_button)
        reply = msg_box.exec()
        if msg_box.clickedButton() == yes_button:
            if self.active_downloads:
                for url in list(self.active_downloads.keys()):
                    self.stop_download(url)  # 다운로드 중단
            self.force_quit = True
            self.quit_application()
            event.accept()
        else:
            event.ignore()

    def quit_application(self):
        self.append_log("프로그램이 완전히 종료됩니다.")
        self.force_quit = True
        for url in list(self.active_downloads.keys()):
            self.stop_download(url)  # 진행 중인 다운로드 중단
        QApplication.quit()

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def append_log(self, text):
        if "[오류]" in text or "[치명적 오류]" in text:
            self.log_output.append(f'<span style="color: #e57373;">{text}</span>')
        elif "완료" in text or "성공" in text:
            self.log_output.append(f'<span style="color: #4caf50;">{text}</span>')
        else:
            self.log_output.append(text)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def on_setup_finished(self, success, ytdlp_exe_path, ffmpeg_exe_path):
        if success:
            self.ytdlp_exe_path = ytdlp_exe_path
            self.ffmpeg_exe_path = ffmpeg_exe_path
            self.append_log("=" * 70)
            self.append_log("📢 [안내] TVer는 일본 지역 제한이 있습니다.")
            self.append_log("📢 원활한 다운로드를 위해 반드시 일본 VPN을 켜고 사용해주세요.")
            self.append_log("=" * 70)
            self.append_log("\n환경 설정 완료. 다운로드를 시작할 수 있습니다.")
            self.url_input.setEnabled(True)
            self.add_button.setEnabled(True)
            self.theme_button.setChecked(self.current_theme == "dark")
        else:
            self.append_log("=" * 70 + "\n[치명적 오류] 환경 설정에 실패했습니다. 로그를 확인하고 프로그램을 재시작하세요.")
            QMessageBox.critical(self, "환경 설정 실패",
                                 "yt-dlp 또는 ffmpeg를 다운로드하지 못했습니다.\n인터넷 연결을 확인하고 다시 시도하세요.")

    def get_download_folder(self):
        return self.config.get("download_folder", "")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택", self.get_download_folder())
        if folder:
            self.config["download_folder"] = folder
            save_config(self.config)
            self.append_log(f"다운로드 폴더가 '{folder}'로 설정되었습니다.")
            return folder
        return None

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = load_config()
            self.apply_stylesheet(self.current_theme)  # 스타일시트 적용 로직 복원
            self.append_log("설정이 저장되었습니다.")

    def process_input_url(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if "/series/" in url:
            self.series_parse_thread = SeriesParseThread(url, self.ytdlp_exe_path)
            self.series_parse_thread.log.connect(self.append_log)
            self.series_parse_thread.finished.connect(self.on_series_parsed)
            self.series_parse_thread.start()
            self.url_input.setEnabled(False)
            self.add_button.setEnabled(False)
        else:
            self.add_url_to_queue(url)
        self.url_input.clear()

    def on_series_parsed(self, episode_urls):
        self.url_input.setEnabled(True)
        self.add_button.setEnabled(True)
        for url, thumbnail_url in episode_urls:  # 썸네일 URL 포함
            self.add_url_to_queue(url, thumbnail_url)

    def add_url_to_queue(self, url, thumbnail_url=None):
        if not url:
            return
        if url in self.active_urls:
            self.append_log(f"[알림] 해당 URL은 이미 대기열에 있거나 다운로드 중입니다: {url}")
            return
        if url in [entry["url"] for entry in self.history]:  # 리스트 기반 중복 체크
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle('중복 다운로드')
            history_entry = next((entry for entry in self.history if entry["url"] == url), {"title": "제목 없음"})
            msg_box.setText(f"이 항목은 이미 다운로드한 기록이 있습니다:\n\n{history_entry['title']}\n\n다시 다운로드하시겠습니까?")
            yes_button = msg_box.addButton("예", QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton("아니오", QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(no_button)
            msg_box.exec()
            if msg_box.clickedButton() == no_button:
                self.append_log(f"[알림] 중복 다운로드를 취소했습니다: {url}")
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
        # 초기 썸네일 URL 전달
        if thumbnail_url:
            widget.update_progress({'thumbnail_url': thumbnail_url})
        self.check_queue_and_start()

    def check_queue_and_start(self):
        while len(self.active_downloads) < self.config.get("max_concurrent_downloads", 3) and self.task_queue:
            task = self.task_queue.pop(0)
            url = task['url']
            download_folder = self.get_download_folder()
            if not download_folder:
                self.append_log("다운로드 폴더가 지정되지 않았습니다. 폴더 선택창을 엽니다...")
                download_folder = self.select_folder()
                if not download_folder:
                    self.append_log(f"'{task['widget'].title_label.text()}' 다운로드가 취소되었습니다. (폴더 미선택)")
                    self.download_list.takeItem(self.download_list.row(task['item']))
                    self.active_urls.remove(url)
                    continue
            parts = self.config.get("filename_parts", {})
            order = self.config.get("filename_order", ["series", "upload_date", "episode_number", "episode", "id"])
            filename_format = " ".join(f"%({key})s" for key in order if parts.get(key, False) and key != 'id')
            if parts.get("id", False):
                filename_format += " [%(id)s]"
            filename_format += ".mp4"
            quality_format = self.config.get("quality", "bv*+ba/b")
            thread = DownloadThread(url, download_folder, self.ytdlp_exe_path, self.ffmpeg_exe_path, filename_format, quality_format)
            thread.progress.connect(self.update_download_progress)
            thread.finished.connect(self.on_download_finished)
            self.active_downloads[url] = {'thread': thread, 'widget': task['widget'], 'item': task['item']}
            thread.start()

    def update_download_progress(self, url, data):
        if url in self.active_downloads:
            self.active_downloads[url]['widget'].update_progress(data)
        if 'log' in data and data['log']:
            self.append_log(data['log'])

    def on_download_finished(self, url, success):
        if url in self.active_downloads:
            widget = self.active_downloads[url]['widget']
            title = widget.title_label.text()
            if success:
                self.append_log(f"--- '{title}' 다운로드 성공 ---")
                add_to_history(self.history, url, {
                    "title": title,
                    "filepath": widget.final_filepath,
                    "date": datetime.now().isoformat()
                })
                self._load_history_items()
            else:
                self.append_log(f"--- '{title}' 다운로드 실패 ---")
            del self.active_downloads[url]
            self.active_urls.remove(url)
        self.check_queue_and_start()
        if not self.active_downloads and not self.task_queue:
            self.on_all_downloads_finished()

    def on_all_downloads_finished(self):
        self.append_log("모든 다운로드가 완료되었습니다.")
        self.append_log("트레이 알림 표시 시도...")
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage("다운로드 완료", "모든 작업이 끝났습니다!", QIcon(get_app_icon()), 5000)
            self.append_log("트레이 알림 표시 요청 완료.")
        else:
            self.append_log("[경고] 시스템 트레이가 사용할 수 없습니다. 대체 알림 표시.")
            QMessageBox.information(self, "다운로드 완료", "모든 작업이 끝났습니다!")
        post_action = self.config.get("post_action", "None")
        if post_action == "Open Folder":
            self.append_log("다운로드 폴더를 엽니다...")
            os.startfile(self.get_download_folder())
        elif post_action == "Shutdown":
            self.append_log("1분 후 시스템을 종료합니다...")
            subprocess.run(["shutdown", "/s", "/t", "60"])

    def stop_download(self, url):
        if url in self.active_downloads:
            self.append_log(f"'{self.active_downloads[url]['widget'].title_label.text()}' 다운로드를 중단합니다...")
            self.active_downloads[url]['thread'].stop()

    def play_file(self, filepath):
        try:
            os.startfile(filepath)
            self.append_log(f"영상 재생: {filepath}")
        except Exception as e:
            self.append_log(f"[오류] 영상 재생 실패: {e}")
            QMessageBox.critical(self, "재생 오류", f"영상 파일을 재생하지 못했습니다: {e}")

    def show_context_menu(self, pos):
        item = self.download_list.itemAt(pos)
        if not item:
            return
        widget = self.download_list.itemWidget(item)
        url = widget.url
        status = widget.status
        menu = QMenu()
        if status == '완료' and widget.final_filepath and os.path.exists(widget.final_filepath):
            open_folder_action = QAction("파일 위치 열기", self)
            open_folder_action.triggered.connect(lambda: open_file_location(widget.final_filepath))
            menu.addAction(open_folder_action)
            play_action = QAction("영상 재생", self)
            play_action.triggered.connect(lambda: self.play_file(widget.final_filepath))
            menu.addAction(play_action)
            menu.addSeparator()
        if status not in ['다운로드 중', '정보 분석 중...', '후처리 중...']:
            remove_action = QAction("목록에서 제거", self)
            remove_action.triggered.connect(lambda: self.remove_item(item, url))
            menu.addAction(remove_action)
        if menu.actions():
            menu.exec(self.download_list.mapToGlobal(pos))

    def remove_item(self, item, url):
        row = self.download_list.row(item)
        self.download_list.takeItem(row)
        self.task_queue = [t for t in self.task_queue if t['url'] != url]
        if url in self.active_urls:
            self.active_urls.remove(url)

    def check_for_updates(self):
        # GitHub Releases API 호출
        url = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            latest_release = response.json()
            latest_version = latest_release["tag_name"].lstrip("v")  # "v" 접두사 제거
            # 버전 파싱: major.minor.patch
            def parse_version(ver):
                parts = ver.split(".")
                return [int(p) if p.isdigit() else 0 for p in parts[:3]] + [0] * (3 - len(parts))
            current_ver_parts = parse_version(self.version)
            latest_ver_parts = parse_version(latest_version)
            # 숫자 비교
            if latest_ver_parts > current_ver_parts:
                reply = QMessageBox.question(
                    self,
                    "업데이트 확인",
                    f"최신 버전 {latest_release['tag_name']}이 있습니다. Releases 페이지로 이동하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl("https://github.com/deuxdoom/TVerDownloader/releases"))
        except requests.RequestException:
            # 네트워크 오류 무시, 알림 생략
            pass

if __name__ == "__main__":
    sys.excepthook = handle_exception
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r')
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())