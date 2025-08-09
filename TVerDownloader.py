# 파일명: TVerDownloader.py
# 메인 UI + 큐/스레드 관리. (테마 스위치 제거, 다크 테마 고정, 다중다운로드 + 즐겨찾기)
import sys
import os
import subprocess
import webbrowser
from typing import Optional, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon,
    QFrame, QSplitter, QTabWidget, QToolButton
)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QCursor, QAction

# 분리 모듈
from src.history_store import HistoryStore
from src.updater import maybe_show_update
from src.qss import build_qss
from src.about_dialog import AboutDialog
from src.bulk_dialog import BulkAddDialog  # ★ 다중 다운로드 다이얼로그
from src.favorites_store import FavoritesStore  # ★ 즐겨찾기 저장소

# 기존 모듈
from src.utils import (
    load_config, save_config,
    handle_exception, open_file_location,
)
from src.icon import get_app_icon
from src.widgets import DownloadItemWidget
from src.workers import SetupThread, SeriesParseThread, DownloadThread
from src.dialogs import SettingsDialog


class MainWindow(QMainWindow):
    LOG_RULE = "=" * 65

    def __init__(self):
        super().__init__()
        self.version = "2.2.0"  # 즐겨찾기 추가
        self.setWindowTitle("티버 다운로더")
        self.resize(1120, 760)
        self.center()
        self.setAcceptDrops(True)
        self.setWindowIcon(get_app_icon())

        # 상태
        self.ytdlp_exe_path = ""
        self.ffmpeg_exe_path = ""
        self.task_queue = []
        self.active_downloads = {}
        self.active_urls = set()

        # 설정
        self.config = load_config()
        self.force_quit = False  # 완전 종료 플래그

        # 기록/즐겨찾기
        self.history_store = HistoryStore("urlhistory.json")
        self.history_store.load()

        self.fav_store = FavoritesStore("favorites.json")     # ★
        self.fav_store.load()

        # 즐겨찾기 확인용 상태
        self._fav_check_queue: List[str] = []                 # ★
        self._fav_current_url: Optional[str] = None           # ★
        self._fav_thread: Optional[SeriesParseThread] = None  # ★

        # 트레이
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("티버 다운로더")
        tray_menu = QMenu()
        restore_action = QAction("창 복원", self); restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("완전 종료", self);  quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(restore_action); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

        # UI
        self._build_ui()
        self.apply_stylesheet()  # 다크 고정

        # 준비 스레드
        self.setup_thread = SetupThread()
        self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")

        # 업데이트 확인
        QTimer.singleShot(300, lambda: maybe_show_update(self, self.version))

    # ================== UI ==================
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # 헤더
        self.header = QFrame(objectName="AppHeader")
        header_layout = QHBoxLayout(self.header); header_layout.setContentsMargins(16,10,16,10); header_layout.setSpacing(8)
        self.app_title = QLabel("티버 다운로더 (TVer Downloader)", objectName="AppTitle")

        self.settings_button = QPushButton("설정", objectName="PrimaryButton")
        self.settings_button.clicked.connect(self.open_settings)

        # 정보(About)
        self.about_button = QPushButton("정보", objectName="PrimaryButton")
        self.about_button.clicked.connect(self.open_about)

        # 항상 위(원형 체크 버튼)
        self.on_top_btn = QToolButton(objectName="OnTopButton")
        self.on_top_btn.setCheckable(True)
        self.on_top_btn.setFixedSize(28, 28)
        self.on_top_btn.setToolTip("항상 위")
        initial_on_top = self.config.get("always_on_top", False)
        self.on_top_btn.setChecked(initial_on_top)
        self.on_top_btn.setText("●" if initial_on_top else "")
        self.on_top_btn.toggled.connect(self.set_always_on_top)

        header_layout.addWidget(self.app_title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.about_button)
        header_layout.addWidget(self.settings_button)
        header_layout.addWidget(self.on_top_btn)

        # 입력바
        self.input_bar = QFrame(objectName="InputBar")
        input_layout = QHBoxLayout(self.input_bar); input_layout.setContentsMargins(16,12,16,12); input_layout.setSpacing(10)
        self.url_input = QLineEdit(placeholderText="TVer 영상 URL 붙여넣기 또는 드래그하세요", objectName="UrlInput")
        self.url_input.returnPressed.connect(self.process_input_url)

        # ★ 다중 다운로드 버튼
        self.bulk_button = QPushButton("다중 다운로드", objectName="PrimaryButton")
        self.bulk_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bulk_button.clicked.connect(self.open_bulk_add)

        self.add_button = QPushButton("다운로드", objectName="AccentButton")
        self.add_button.clicked.connect(self.process_input_url)

        input_layout.addWidget(self.url_input, 1)
        input_layout.addWidget(self.bulk_button, 0)
        input_layout.addWidget(self.add_button, 0)

        # 탭
        self.tabs = QTabWidget(objectName="MainTabs")

        # [다운로드] 좌 리스트 / 우 로그
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
        self.clear_log_button.clicked.connect(self.clear_log)
        log_row.addWidget(self.log_title); log_row.addStretch(1); log_row.addWidget(self.clear_log_button)
        self.log_output = QTextEdit(objectName="LogOutput"); self.log_output.setReadOnly(True); self.log_output.setAcceptRichText(True)
        right_layout.addLayout(log_row)
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

        # [즐겨찾기] ★ 추가
        self.fav_tab = QWidget(objectName="FavoritesTab")
        fav_layout = QVBoxLayout(self.fav_tab); fav_layout.setContentsMargins(12,12,12,12); fav_layout.setSpacing(8)

        fav_top = QHBoxLayout(); fav_top.setContentsMargins(0,0,0,0); fav_top.setSpacing(6)
        self.fav_title = QLabel("즐겨찾기(시리즈)", objectName="PaneTitle")
        self.fav_subtitle = QLabel("등록된 시리즈의 새 에피소드를 자동으로 확인/다운로드", objectName="PaneSubtitle")
        fav_top.addWidget(self.fav_title); fav_top.addStretch(1); fav_top.addWidget(self.fav_subtitle)
        fav_layout.addLayout(fav_top)

        fav_ctrl = QHBoxLayout(); fav_ctrl.setContentsMargins(0,0,0,0); fav_ctrl.setSpacing(6)
        self.fav_input = QLineEdit(placeholderText="TVer 시리즈 URL (예: https://tver.jp/series/....)")
        self.fav_add_btn = QPushButton("추가");   self.fav_add_btn.clicked.connect(self.add_favorite)
        self.fav_del_btn = QPushButton("삭제");   self.fav_del_btn.clicked.connect(self.remove_selected_favorite)
        self.fav_chk_btn = QPushButton("전체 확인"); self.fav_chk_btn.clicked.connect(self.check_all_favorites)
        fav_ctrl.addWidget(self.fav_input, 1); fav_ctrl.addWidget(self.fav_add_btn); fav_ctrl.addWidget(self.fav_del_btn); fav_ctrl.addWidget(self.fav_chk_btn)
        fav_layout.addLayout(fav_ctrl)

        self.fav_list = QListWidget(objectName="FavoritesList")
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_list.customContextMenuRequested.connect(self.show_fav_menu)
        fav_layout.addWidget(self.fav_list, 1)

        self.tabs.addTab(self.download_tab, "다운로드")
        self.tabs.addTab(self.history_tab, "기록")
        self.tabs.addTab(self.fav_tab, "즐겨찾기")  # ★

        root.addWidget(self.header); root.addWidget(self.input_bar); root.addWidget(self.tabs, 1)

        version_label = QLabel(f"Version: {self.version}"); version_label.setObjectName("VersionLabel")
        self.statusBar().addPermanentWidget(version_label)

        self.url_input.setEnabled(False); self.add_button.setEnabled(False)

        self.refresh_history_list()
        self.refresh_fav_list()  # ★
        # 항상 위 초기 반영
        self.set_always_on_top(self.on_top_btn.isChecked())

    # ================== 스타일 ==================
    def apply_stylesheet(self):
        # 다크 테마 고정
        self.setStyleSheet(build_qss())

    # ================== 트레이/종료 ==================
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.append_log("트레이 아이콘 더블클릭으로 창 복원됨.")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray_icon.showMessage("티버 다운로더", "프로그램이 트레이로 이동했습니다.", get_app_icon(), 2000)
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
        self.log_output.clear()

    # ================== About ==================
    def open_about(self):
        dlg = AboutDialog(version=self.version, parent=self)
        dlg.exec()

    # ================== 항상 위 ==================
    def set_always_on_top(self, enabled: bool):
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        if hasattr(self, "on_top_btn"):
            self.on_top_btn.setText("●" if enabled else "")
        self.config["always_on_top"] = enabled
        save_config(self.config)

    # ================== 준비 완료 ==================
    def on_setup_finished(self, success: bool, ytdlp_exe_path: str, ffmpeg_exe_path: str):
        if success:
            self.ytdlp_exe_path = ytdlp_exe_path
            self.ffmpeg_exe_path = ffmpeg_exe_path
            self.append_log(self.LOG_RULE)
            self.append_log("📢 [안내] TVer는 일본 지역 제한이 있습니다.")
            self.append_log("📢 원활한 다운로드를 위해 반드시 일본 VPN을 켜고 사용해주세요.")
            self.append_log(self.LOG_RULE)
            self.append_log("\n환경 설정 완료. 다운로드를 시작할 수 있습니다.")
            self.url_input.setEnabled(True)
            self.add_button.setEnabled(True)

            # ★ 시작 시 즐겨찾기 자동 확인
            if self.config.get("auto_check_favorites_on_start", True):
                QTimer.singleShot(1200, self.check_all_favorites)

        else:
            self.append_log(self.LOG_RULE + "\n[치명적 오류] 환경 설정 실패. 로그를 확인하고 재시작하세요.")
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
            self.apply_stylesheet()  # 다크 고정
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

    # ★★★ 다중 다운로드 UI/로직 ★★★
    def open_bulk_add(self):
        """다중 URL 입력 다이얼로그 열기"""
        dlg = BulkAddDialog(self)
        if dlg.exec():
            urls = dlg.get_urls()  # List[str] 기대
            self.add_urls_to_queue(urls)

    def add_urls_to_queue(self, urls: List[str]):
        """여러 URL을 한 번에 추가"""
        if not urls: return
        added = 0
        for u in urls:
            u = (u or "").strip()
            if not u: continue
            self.add_url_to_queue(u)
            added += 1
        if added:
            self.append_log(f"[알림] 다중 추가: {added}개 URL 대기열에 등록됨.")

    # 드래그 앤 드롭으로 .txt 파일에서 일괄 추가 지원
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        try:
            if e.mimeData().hasUrls():
                local_files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
                txts = [p for p in local_files if p.lower().endswith(".txt")]
                if txts:
                    total = 0
                    for path in txts:
                        urls = self._read_urls_from_txt(path)
                        self.add_urls_to_queue(urls)
                        total += len(urls)
                    if total:
                        self.append_log(f"[알림] TXT에서 {total}개 URL 추가됨.")
                else:
                    # 드래그된 게 일반 파일이 아니거나 txt가 아니면 무시 (개별 URL은 입력창으로)
                    pass
            e.acceptProposedAction()
        except Exception as ex:
            self.append_log(f"[오류] 드롭 처리 실패: {ex}")

    def _read_urls_from_txt(self, path: str) -> List[str]:
        """텍스트 파일에서 URL 라인 파싱(공백/중복/주석 제거)"""
        urls: List[str] = []
        seen = set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith("#"):  # 빈 줄/주석 제외
                        continue
                    if s not in seen:
                        seen.add(s)
                        urls.append(s)
        except UnicodeDecodeError:
            # CP949 등 현지 인코딩 재시도
            with open(path, "r", encoding="cp949", errors="ignore") as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith("#"):
                        continue
                    if s not in seen:
                        seen.add(s)
                        urls.append(s)
        return urls

    # ================== 다운로드 큐 ==================
    def add_url_to_queue(self, url: str):
        if not url: return
        if url in self.active_urls:
            self.append_log(f"[알림] 이미 대기열/다운로드 중: {url}"); return

        if self.history_store.exists(url):
            title_preview = self.history_store.get_title(url)
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
            filename_format = " ".join(f"%({key})s" for key in order if parts.get(key, False) and key != 'id')
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
                self.history_store.add(url, title)
                self.refresh_history_list()
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

    # ================== 기록 탭 ==================
    def refresh_history_list(self):
        self.history_list.clear()
        for url, meta in self.history_store.sorted_entries():
            title = meta.get("title", "(제목 없음)")
            date = meta.get("date", "")
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
        self.history_store.remove(url)
        self.refresh_history_list()
        self.append_log(f"[알림] 기록에서 제거됨: {url}")

    # ================== 즐겨찾기 탭 ==================
    def refresh_fav_list(self):
        self.fav_list.clear()
        for url, meta in self.fav_store.sorted_entries():
            added = meta.get("added", "")
            last = meta.get("last_check", "")
            txt = f"{url}\n추가: {added}   마지막 확인: {last or '-'}"
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, url)
            self.fav_list.addItem(item)

    def add_favorite(self):
        url = (self.fav_input.text() or "").strip()
        if not url or "/series/" not in url:
            QMessageBox.information(self, "알림", "유효한 TVer 시리즈 URL을 입력하세요.\n예: https://tver.jp/series/....")
            return
        if self.fav_store.exists(url):
            QMessageBox.information(self, "알림", "이미 즐겨찾기에 있습니다.")
            return
        self.fav_store.add(url)
        self.fav_input.clear()
        self.refresh_fav_list()
        self.append_log(f"[즐겨찾기] 추가: {url}")

    def remove_selected_favorite(self):
        items = self.fav_list.selectedItems()
        if not items:
            return
        for it in items:
            url = it.data(Qt.ItemDataRole.UserRole)
            self.fav_store.remove(url)
            self.append_log(f"[즐겨찾기] 삭제: {url}")
        self.refresh_fav_list()

    def show_fav_menu(self, pos):
        item = self.fav_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu()
        a1 = QAction("이 시리즈 확인", self); a1.triggered.connect(lambda: self.check_single_favorite(url)); menu.addAction(a1)
        a2 = QAction("브라우저에서 열기", self); a2.triggered.connect(lambda: webbrowser.open(url)); menu.addAction(a2)
        menu.addSeparator()
        a3 = QAction("즐겨찾기에서 제거", self); a3.triggered.connect(lambda: (self.fav_store.remove(url), self.refresh_fav_list())); menu.addAction(a3)
        menu.exec(self.fav_list.mapToGlobal(pos))

    def check_all_favorites(self):
        """등록된 모든 시리즈를 순차 확인"""
        if self._fav_thread:  # 이미 진행 중이면 무시
            self.append_log("[즐겨찾기] 확인 작업이 이미 진행 중입니다.")
            return
        series_list = self.fav_store.list_series()
        if not series_list:
            self.append_log("[즐겨찾기] 등록된 시리즈가 없습니다.")
            return
        self._fav_check_queue = list(series_list)
        self.append_log(f"[즐겨찾기] 전체 확인 시작: {len(self._fav_check_queue)}개 시리즈")
        self._run_next_fav()

    def check_single_favorite(self, series_url: str):
        """단일 시리즈만 확인"""
        if self._fav_thread:
            self.append_log("[즐겨찾기] 다른 확인 작업이 진행 중입니다. 잠시 후 다시 시도하세요.")
            return
        self._fav_check_queue = [series_url]
        self.append_log(f"[즐겨찾기] 시리즈 확인: {series_url}")
        self._run_next_fav()

    def _run_next_fav(self):
        if not self._fav_check_queue:
            self.append_log("[즐겨찾기] 확인 완료.")
            self._fav_current_url = None
            self._fav_thread = None
            return

        self._fav_current_url = self._fav_check_queue.pop(0)
        self._fav_thread = SeriesParseThread(self._fav_current_url, self.ytdlp_exe_path)
        self._fav_thread.log.connect(self.append_log)
        self._fav_thread.finished.connect(self._on_fav_series_parsed)
        self._fav_thread.start()

    def _on_fav_series_parsed(self, episode_urls: List[str]):
        series_url = self._fav_current_url or ""
        try:
            already_in_queue = {t['url'] for t in self.task_queue}
            added = 0
            for ep in episode_urls:
                # 히스토리에 있거나, 이미 대기/진행 중이면 스킵
                if self.history_store.exists(ep): 
                    continue
                if ep in self.active_urls or ep in already_in_queue:
                    continue
                self.add_url_to_queue(ep)
                added += 1

            self.append_log(f"[즐겨찾기] {series_url} → 신규 {added}개 큐에 추가")
            self.fav_store.touch_last_check(series_url)
            self.refresh_fav_list()
        finally:
            self._fav_thread = None
            self._run_next_fav()


if __name__ == "__main__":
    sys.excepthook = handle_exception
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r')
    app = QApplication(sys.argv)

    # 전역 다크 테마 적용 (themes.py 없이 직접)
    from src.qss import build_qss
    app.setStyle("")         # 초기화
    app.setStyle("Fusion")   # 플랫폼 편차 줄이기
    app.setStyleSheet(build_qss())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
