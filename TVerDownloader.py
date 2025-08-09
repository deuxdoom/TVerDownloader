# -*- coding: utf-8 -*-
# 메인 UI + 큐/스레드 제어 (2.2.0 베이스, 버전/배너/동시다운/히스토리·즐겨찾기 보완)
# - 내부 앱 이름: 한글 "티버 다운로더"
# - 윈도우 타이틀/트레이 툴팁: 영문 + 버전 "TVer Downloader v2.3.0"
# - AboutDialog에는 문자열 버전(APP_VERSION)을 명시적으로 전달

import sys
import os
import subprocess
import webbrowser
from typing import Optional, List, Dict, Set

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon,
    QFrame, QSplitter, QTabWidget, QToolButton
)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QCursor, QAction, QGuiApplication

from src.utils import load_config, save_config, handle_exception, open_file_location
from src.icon import get_app_icon
from src.qss import build_qss
from src.about_dialog import AboutDialog
from src.bulk_dialog import BulkAddDialog
from src.dialogs import SettingsDialog

from src.history_store import HistoryStore
from src.favorites_store import FavoritesStore

from src.widgets import DownloadItemWidget
from src.workers import SetupThread, SeriesParseThread, DownloadThread


# ===== 앱 메타 =====
APP_NAME_KO = "티버 다운로더"        # 내부 표기
APP_NAME_EN = "TVer Downloader"     # 타이틀/툴팁 표기
APP_VERSION = "v2.3.0"              # 요청 버전

class MainWindow(QMainWindow):
    LOG_RULE = "=" * 44
    PARALLEL_MIN = 1
    PARALLEL_MAX = 5
    PARALLEL_DEFAULT = 3

    def __init__(self):
        super().__init__()
        # 타이틀은 영문 + 버전
        self.setWindowTitle(f"{APP_NAME_EN} {APP_VERSION}")
        self.setWindowIcon(get_app_icon())
        self.resize(1100, 700)

        # 외부 도구 경로(SetupThread에서 채워짐)
        self.ytdlp_exe_path: Optional[str] = None
        self.ffmpeg_exe_path: Optional[str] = None
        self.env_ready = False

        # 상태
        self.task_queue: List[Dict] = []
        self.active_downloads: Dict[str, Dict] = {}   # url -> {'thread', 'item', 'widget'}
        self.active_urls: Set[str] = set()
        self._start_logged: Set[str] = set()

        # 설정
        self.config = load_config()
        self._canonicalize_parallel_config(persist=True)
        self.force_quit = False

        # 저장소
        self.history_store = HistoryStore("urlhistory.json"); self.history_store.load()
        self.fav_store = FavoritesStore("favorites.json", related_history_path="urlhistory.json"); self.fav_store.load()

        # UI
        self._build_ui()
        self._set_input_enabled(False)
        self._init_tray()

        # 시작 로그
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")

        # 준비 스레드
        self.setup_thread = SetupThread()
        self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()

        # 초기 리스트 반영
        self.refresh_history_list()
        self.refresh_fav_list()

        self.set_always_on_top(self.config.get("always_on_top", False))
        QTimer.singleShot(1500, self._maybe_update_notice)

        # ---- Bulk 시리즈 파서 상태 ----
        self._bulk_series_queue: List[str] = []
        self._bulk_thread: Optional[SeriesParseThread] = None
        self._bulk_added_total: int = 0

        # ---- 즐겨찾기 자동 확인 상태 ----
        self._auto_series_queue: List[str] = []
        self._auto_thread: Optional[SeriesParseThread] = None
        self._auto_added_total: int = 0

    # ================== UI 빌드 ==================
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # 헤더
        self.header = QFrame(objectName="AppHeader")
        header_layout = QHBoxLayout(self.header); header_layout.setContentsMargins(16,10,16,10); header_layout.setSpacing(8)
        # 내부 표기는 한글 앱명(영문 병기)
        self.app_title = QLabel(f"{APP_NAME_KO} ({APP_NAME_EN})", objectName="AppTitle")

        self.about_button = QPushButton("정보", objectName="PrimaryButton")
        self.about_button.clicked.connect(self.open_about)

        self.settings_button = QPushButton("설정", objectName="PrimaryButton")
        self.settings_button.clicked.connect(self.open_settings)

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
        self.url_input = QLineEdit(placeholderText="TVer 영상 URL 붙여넣기 또는 드래그", objectName="UrlInput")
        self.url_input.returnPressed.connect(self.process_input_url)

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

        # 다운로드 탭
        self.download_tab = QWidget(objectName="DownloadTab")
        dl_layout = QVBoxLayout(self.download_tab); dl_layout.setContentsMargins(12,12,12,12); dl_layout.setSpacing(8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, objectName="MainSplitter")
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

        # 기록 탭
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

        # 즐겨찾기 탭
        self.fav_tab = QWidget(objectName="FavoritesTab")
        fav_layout = QVBoxLayout(self.fav_tab); fav_layout.setContentsMargins(12,12,12,12); fav_layout.setSpacing(8)

        fav_top = QHBoxLayout(); fav_top.setContentsMargins(0,0,0,0); fav_top.setSpacing(6)
        self.fav_title = QLabel("즐겨찾기(시리즈)", objectName="PaneTitle")
        self.fav_subtitle = QLabel("등록된 시리즈의 새 에피소드를 확인/다운로드", objectName="PaneSubtitle")
        fav_top.addWidget(self.fav_title); fav_top.addStretch(1); fav_top.addWidget(self.fav_subtitle)
        fav_layout.addLayout(fav_top)

        fav_ctrl = QHBoxLayout(); fav_ctrl.setContentsMargins(0,0,0,0); fav_ctrl.setSpacing(6)
        self.fav_input = QLineEdit(placeholderText="TVer 시리즈 URL (예: https://tver.jp/series/....)")
        self.fav_add_btn = QPushButton("추가", objectName="PrimaryButton");   self.fav_add_btn.clicked.connect(self.add_favorite)
        self.fav_del_btn = QPushButton("삭제", objectName="DangerButton");   self.fav_del_btn.clicked.connect(self.remove_selected_favorite)
        self.fav_chk_btn = QPushButton("전체 확인", objectName="AccentButton"); self.fav_chk_btn.clicked.connect(self.check_all_favorites)
        fav_ctrl.addWidget(self.fav_input, 1); fav_ctrl.addWidget(self.fav_add_btn); fav_ctrl.addWidget(self.fav_del_btn); fav_ctrl.addWidget(self.fav_chk_btn)
        fav_layout.addLayout(fav_ctrl)

        self.fav_list = QListWidget(objectName="FavoritesList")
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_list.customContextMenuRequested.connect(self.show_fav_menu)
        fav_layout.addWidget(self.fav_list, 1)

        self.tabs.addTab(self.download_tab, "다운로드")
        self.tabs.addTab(self.history_tab, "기록")
        self.tabs.addTab(self.fav_tab, "즐겨찾기")

        root.addWidget(self.header); root.addWidget(self.input_bar); root.addWidget(self.tabs, 1)

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip(f"{APP_NAME_EN} {APP_VERSION}")
        tray_menu = QMenu()
        restore_action = QAction("창 복원", self); restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("완전 종료", self);  quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(restore_action); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    # ================== 공통 유틸 ==================
    def _set_input_enabled(self, enabled: bool):
        self.url_input.setEnabled(enabled)
        self.add_button.setEnabled(enabled)
        self.bulk_button.setEnabled(enabled)

    def append_log(self, text: str):
        if "[오류]" in text or "[치명적 오류]" in text:
            self.log_output.append(f'<span style="color: #EF4444;">{text}</span>')
        elif "완료" in text or "성공" in text:
            self.log_output.append(f'<span style="color: #22C55E;">{text}</span>')
        else:
            self.log_output.append(text)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def clear_log(self):
        self.log_output.clear()

    # --------- 동시 다운로드 갯수 정규화 ---------
    def _canonicalize_parallel_config(self, persist: bool = False) -> int:
        def clamp(n: int) -> int:
            return max(self.PARALLEL_MIN, min(self.PARALLEL_MAX, int(n)))
        val = self.config.get("max_parallel")
        if isinstance(val, (int, float, str)):
            try:
                v = clamp(int(float(val)))
                self.config["max_parallel"] = v
                if persist: save_config(self.config)
                return v
            except Exception:
                pass
        for k in ["max_parallel_downloads", "parallel_downloads", "concurrent_downloads", "max_concurrent",
                  "concurrency", "maxConcurrentDownloads"]:
            if k in self.config:
                try:
                    v = clamp(int(float(self.config[k])))
                    self.config["max_parallel"] = v
                    if persist: save_config(self.config)
                    return v
                except Exception:
                    pass
        for c in ["downloads", "download", "settings", "general", "app"]:
            d = self.config.get(c)
            if isinstance(d, dict):
                for k in ["max_parallel", "parallel", "concurrent", "max"]:
                    if k in d:
                        try:
                            v = clamp(int(float(d[k])))
                            self.config["max_parallel"] = v
                            if persist: save_config(self.config)
                            return v
                        except Exception:
                            continue
        self.config["max_parallel"] = self.PARALLEL_DEFAULT
        if persist: save_config(self.config)
        return self.PARALLEL_DEFAULT

    def get_max_parallel(self) -> int:
        try:
            v = int(self.config.get("max_parallel", self.PARALLEL_DEFAULT))
            return max(self.PARALLEL_MIN, min(self.PARALLEL_MAX, v))
        except Exception:
            return self.PARALLEL_DEFAULT

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
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        QApplication.quit()

    def set_always_on_top(self, on: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()
        self.on_top_btn.setText("●" if on else "")
        self.config["always_on_top"] = bool(on)
        save_config(self.config)

    def get_download_folder(self) -> Optional[str]:
        folder = self.config.get("download_folder")
        if folder and os.path.isdir(folder):
            return folder
        folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택")
        if folder:
            self.config["download_folder"] = folder; save_config(self.config)
            self.append_log(f"다운로드 폴더가 '{folder}'로 설정되었습니다.")
            return folder
        return None

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = load_config()
            v = self._canonicalize_parallel_config(persist=True)
            self.append_log(f"설정이 저장되었습니다. 동시 다운로드:  {v}개")
            self.check_queue_and_start()

    def open_about(self):
        # 2.2.0 베이스 설계: 버전 문자열을 인자로 전달해야 함
        AboutDialog(APP_VERSION, self).exec()

    # ================== 다중 추가(시리즈 확장 지원) ==================
    def open_bulk_add(self):
        if not self._ensure_ready():
            return
        dlg = BulkAddDialog(self)
        if dlg.exec():
            urls = dlg.get_urls()
            self._handle_bulk_urls(urls)

    def _handle_bulk_urls(self, urls: List[str]):
        urls = self._normalize_urls(urls)
        if not urls:
            QMessageBox.information(self, "알림", "유효한 URL이 없습니다."); return

        normal: List[str] = []
        series: List[str] = []
        for u in urls:
            (series if "/series/" in u else normal).append(u)

        added_norm = 0
        for u in normal:
            if self.add_url_to_queue(u):
                added_norm += 1

        self._bulk_series_queue = series[:]
        self._bulk_added_total = 0
        if series:
            self.append_log(f"[다중] 시리즈 {len(series)}개 확장 시작…")
            self._bulk_run_next_series()
        elif added_norm:
            self.append_log(f"[다중] 일반 URL {added_norm}개 대기열 추가 완료.")

    def _bulk_run_next_series(self):
        if self._bulk_thread or not self._bulk_series_queue:
            if not self._bulk_series_queue and not self._bulk_thread:
                self.append_log(f"[다중] 시리즈 확장 완료: 총 {self._bulk_added_total}개 에피소드 추가")
            return
        series_url = self._bulk_series_queue.pop(0)
        self._bulk_thread = SeriesParseThread(series_url, self.ytdlp_exe_path)
        self._bulk_thread.log.connect(self.append_log)
        self._bulk_thread.finished.connect(self._on_bulk_series_parsed)
        self._bulk_thread.start()

    def _on_bulk_series_parsed(self, episode_urls: List[str] | None):
        try:
            eps = episode_urls or []
            added = 0
            for u in eps:
                if self.add_url_to_queue(u):
                    added += 1
            self._bulk_added_total += added
            self.append_log(f"[다중] 시리즈 확장 → {added}개 추가")
        finally:
            self._bulk_thread = None
            self._bulk_run_next_series()

    # ================== URL 처리 ==================
    def _ensure_ready(self) -> bool:
        if not self.env_ready or not self.ytdlp_exe_path or not self.ffmpeg_exe_path:
            QMessageBox.information(self, "알림", "초기 준비 중입니다. 잠시만 기다리세요.")
            return False
        return True

    def _normalize_urls(self, urls: List[str]) -> List[str]:
        seen = set(); out: List[str] = []
        for u in urls or []:
            s = (u or "").strip()
            if s and s not in seen:
                seen.add(s); out.append(s)
        return out

    def process_input_url(self):
        if not self._ensure_ready():
            return
        url = (self.url_input.text() or "").strip()
        if not url:
            return
        if "/series/" in url:
            self.series_parse_thread = SeriesParseThread(url, self.ytdlp_exe_path)
            self.series_parse_thread.log.connect(self.append_log)
            self.series_parse_thread.finished.connect(self.on_series_parsed)
            self.series_parse_thread.start()
            self.url_input.setEnabled(False); self.add_button.setEnabled(False)
        else:
            self.add_url_to_queue(url)
        self.url_input.clear()

    def on_series_parsed(self, episode_urls: List[str] | None):
        self.url_input.setEnabled(True); self.add_button.setEnabled(True)
        eps = episode_urls or []
        if not eps:
            self.append_log("[알림] 시리즈에서 가져올 에피소드가 없습니다.")
            return
        added = 0
        for url in eps:
            if self.add_url_to_queue(url):
                added += 1
        self.append_log(f"[알림] 시리즈에서 {added}개 대기열에 추가되었습니다.")

    # ================== 컨텍스트 메뉴 ==================
    def show_context_menu(self, pos):
        item = self.download_list.itemAt(pos)
        if not item:
            return
        widget = self.download_list.itemWidget(item)
        url = getattr(widget, "url", None)
        status_text = getattr(widget, "status", "") or widget.status_label.text()

        menu = QMenu()

        if url in self.active_downloads:
            act_stop = QAction("중지", self)
            act_stop.triggered.connect(lambda: self.stop_download(url))
            menu.addAction(act_stop)
        else:
            # 대기 항목이면 제거
            if self._queue_index(url) != -1:
                act_rm_q = QAction("대기에서 제거", self)
                act_rm_q.triggered.connect(lambda: self._remove_from_queue(url))
                menu.addAction(act_rm_q)

            # 완료/오류/취소/중단 항목은 목록에서 삭제 가능
            if status_text in ("완료", "오류", "실패", "취소", "중단"):
                act_rm_it = QAction("목록에서 삭제", self)
                act_rm_it.triggered.connect(lambda: self._remove_item_from_list(url))
                menu.addAction(act_rm_it)

        if getattr(widget, "final_filepath", None):
            act_open = QAction("폴더 열기", self)
            act_open.triggered.connect(lambda: open_file_location(widget.final_filepath))
            menu.addAction(act_open)

        menu.exec(self.download_list.mapToGlobal(pos))

    # ================== 큐/다운로드 ==================
    def add_url_to_queue(self, url: str) -> bool:
        url = (url or "").strip()
        if not url:
            return False
        if url in self.active_urls:
            self.append_log(f"[알림] 이미 대기열/다운로드 중: {url}")
            return False

        # 중복 경고(히스토리)
        if self.history_store.exists(url):
            title_preview = self.history_store.get_title(url)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle('중복 다운로드')
            msg_box.setText(f"이미 다운로드한 항목입니다:\n\n{title_preview}\n\n다시 다운로드할까요?")
            yes_button = msg_box.addButton("예", QMessageBox.ButtonRole.YesRole)
            no_button = msg_box.addButton("아니오", QMessageBox.ButtonRole.NoRole)
            msg_box.setDefaultButton(no_button)
            msg_box.exec()
            if msg_box.clickedButton() == no_button:
                self.append_log(f"[알림] 중복 다운로드 취소: {url}")
                return False

        self.active_urls.add(url)
        item = QListWidgetItem()
        widget = DownloadItemWidget(url)
        widget.play_requested.connect(self.play_file)
        item.setSizeHint(widget.sizeHint())
        self.download_list.insertItem(0, item)
        self.download_list.setItemWidget(item, widget)
        self.task_queue.append({'item': item, 'widget': widget, 'url': url})
        self._update_queue_counter()
        self.append_log(f"[대기열] 추가: {url}")
        self.check_queue_and_start()
        return True

    def _update_queue_counter(self):
        running = len(self.active_downloads)
        queued = len(self.task_queue)
        self.queue_count.setText(f"{queued} 대기 / {running} 진행")

    def check_queue_and_start(self):
        if not self.task_queue:
            return
        max_parallel = self.get_max_parallel()
        running = len(self.active_downloads)
        started = 0
        while self.task_queue and running < max_parallel:
            task = self.task_queue.pop(0)
            item, widget, url = task['item'], task['widget'], task['url']
            self._start_download(item, widget, url)
            running += 1
            started += 1
        if started:
            self.append_log(f"[대기열] {started}개 시작 (동시 {max_parallel}개 제한)")
        self._update_queue_counter()

    def _start_download(self, item: QListWidgetItem, widget: DownloadItemWidget, url: str):
        if not self._ensure_ready():
            return
        download_folder = self.get_download_folder()
        if not download_folder:
            self.append_log("[오류] 다운로드 폴더가 설정되지 않았습니다.")
            return

        filename_format = self.config.get("filename_format", "%(title)s [%(id)s].%(ext)s")
        quality_format  = self.config.get("quality_format", "bestvideo+bestaudio/best")

        t = DownloadThread(url, download_folder, self.ytdlp_exe_path, self.ffmpeg_exe_path, filename_format, quality_format)
        t.progress.connect(self.on_download_progress)
        t.finished.connect(self.on_download_finished)

        self.active_downloads[url] = {'thread': t, 'item': item, 'widget': widget}
        self._start_logged.discard(url)
        t.start()

    def on_download_progress(self, url: str, payload: dict):
        entry = self.active_downloads.get(url)
        if not entry:
            return
        widget: DownloadItemWidget = entry['widget']

        if url not in self._start_logged:
            self._start_logged.add(url)
            self.append_log(f"{self.LOG_RULE}\n다운로드 시작: {url}\n{self.LOG_RULE}")

        widget.update_progress(payload)
        if payload.get('log'):
            self.append_log(payload['log'])

    def on_download_finished(self, url: str, success: bool):
        entry = self.active_downloads.pop(url, None)
        if not entry:
            return
        widget: DownloadItemWidget = entry['widget']

        if success:
            widget.update_progress({'status': '완료', 'progress': 100})
            title_text = widget.title_label.text()
            self.history_store.add(url, title_text)
            self.history_store.save()
            self.refresh_history_list()
            self.append_log(f"[성공] 다운로드 완료: {title_text}\n{url}")
        else:
            widget.update_progress({'status': '오류'})
            self.append_log(f"[오류] 다운로드 실패: {url}")

        if url in self.active_urls:
            self.active_urls.remove(url)
        self._start_logged.discard(url)
        self._update_queue_counter()

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

    def play_file(self, filepath: str):
        try:
            os.startfile(filepath)
            self.append_log(f"영상 재생: {filepath}")
        except Exception as e:
            self.append_log(f"[오류] 재생 실패: {e}")

    def stop_download(self, url: str):
        if url in self.active_downloads:
            title = self.active_downloads[url]['widget'].title_label.text()
            self.append_log(f"'{title}' 다운로드 중단...")
            self.active_downloads[url]['thread'].stop()

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
        act_copy = QAction("URL 링크 복사", self)
        act_copy.triggered.connect(lambda: self._copy_to_clipboard(url))
        menu.addAction(act_copy)
        redl = QAction("다시 다운로드", self); redl.triggered.connect(lambda: self.add_url_to_queue(url)); menu.addAction(redl)
        rm = QAction("기록에서 제거", self); rm.triggered.connect(lambda: self.remove_from_history(url)); menu.addAction(rm)
        menu.exec(self.history_list.mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str):
        try:
            QGuiApplication.clipboard().setText(text or "")
            self.append_log("URL이 클립보드로 복사되었습니다.")
        except Exception as e:
            self.append_log(f"[오류] 클립보드 복사 실패: {e}")

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
        a3 = QAction("삭제", self); a3.triggered.connect(lambda: self._remove_favorite_via_menu(url)); menu.addAction(a3)
        menu.exec(self.fav_list.mapToGlobal(pos))

    def _remove_favorite_via_menu(self, url: str):
        self.fav_store.remove(url)
        self.refresh_fav_list()
        self.append_log(f"[즐겨찾기] 삭제: {url}")

    def check_single_favorite(self, series_url: str):
        if not self._ensure_ready():
            return
        self.append_log(f"[즐겨찾기] 전체 확인 시작: 1개 시리즈")
        self._fav_check_queue = [series_url]
        self._run_next_fav(final_log=True)

    def check_all_favorites(self):
        if not self._ensure_ready():
            return
        self._fav_check_queue = self.fav_store.list_series()
        self.append_log(f"[즐겨찾기] 전체 확인 시작: {len(self._fav_check_queue)}개 시리즈")
        if not self._fav_check_queue:
            QMessageBox.information(self, "알림", "등록된 즐겨찾기가 없습니다."); 
            self.append_log("[즐겨찾기] 확인 완료.")
            return
        self._run_next_fav(final_log=True)

    def _run_next_fav(self, *, final_log: bool = False):
        if getattr(self, "_fav_thread", None) or not getattr(self, "_fav_check_queue", []):
            if final_log and not getattr(self, "_fav_thread", None) and not getattr(self, "_fav_check_queue", []):
                self.append_log("[즐겨찾기] 확인 완료.")
            return
        series_url = self._fav_check_queue.pop(0)
        self._fav_current_url = series_url
        self.append_log(f"시리즈 URL 분석 중: {series_url}")
        self._fav_thread = SeriesParseThread(series_url, self.ytdlp_exe_path)
        self._fav_thread.log.connect(self.append_log)
        self._fav_thread.finished.connect(lambda eps: self._on_fav_parsed(eps, final_log=final_log))
        self._fav_thread.start()

    def _on_fav_parsed(self, episode_urls: List[str] | None, *, final_log: bool):
        try:
            series_url = getattr(self, "_fav_current_url", "")
            eps = episode_urls or []
            self.append_log(f"시리즈에서 {len(eps)}개의 에피소드를 찾았습니다. 예고편을 제외합니다...")
            self.append_log(f"최종적으로 {len(eps)}개의 에피소드를 다운로드 목록에 추가합니다.")
            added = 0
            for url in eps:
                if self.add_url_to_queue(url):
                    added += 1
            self.append_log(f"[즐겨찾기] {series_url} → 신규 {added}개 큐에 추가")
            # 마지막 확인 갱신(저장은 FavoritesStore가 처리)
            self.fav_store.touch_last_check(series_url)
            self.refresh_fav_list()
        finally:
            self._fav_thread = None
            self._run_next_fav(final_log=final_log)

    # ---------- 시작 시 즐겨찾기 자동 확인 ----------
    def _auto_check_favorites_on_start(self):
        self._auto_series_queue = self.fav_store.list_series()
        self._auto_added_total = 0
        self.append_log(f"[즐겨찾기] 전체 확인 시작: {len(self._auto_series_queue)}개 시리즈")
        if not self._auto_series_queue:
            self.append_log("[즐겨찾기] 확인 완료.")
            return
        self._auto_run_next()

    def _auto_run_next(self):
        if self._auto_thread or not self._auto_series_queue:
            if not self._auto_series_queue and not self._auto_thread:
                self.append_log("[즐겨찾기] 확인 완료.")
            return
        series_url = self._auto_series_queue.pop(0)
        self._auto_current_url = series_url
        self.append_log(f"시리즈 URL 분석 중: {series_url}")
        self._auto_thread = SeriesParseThread(series_url, self.ytdlp_exe_path)
        self._auto_thread.log.connect(self.append_log)
        self._auto_thread.finished.connect(self._on_auto_parsed)
        self._auto_thread.start()

    def _on_auto_parsed(self, episode_urls: List[str] | None):
        try:
            series_url = getattr(self, "_auto_current_url", "")
            eps = episode_urls or []
            self.append_log(f"시리즈에서 {len(eps)}개의 에피소드를 찾았습니다. 예고편을 제외합니다...")
            self.append_log(f"최종적으로 {len(eps)}개의 에피소드를 다운로드 목록에 추가합니다.")
            added = 0
            for u in eps:
                if not self.history_store.exists(u) and u not in self.active_urls:
                    if self.add_url_to_queue(u):
                        added += 1
            self._auto_added_total += added
            self.append_log(f"[즐겨찾기] {series_url} → 신규 {added}개 큐에 추가")
            # 마지막 확인 갱신(저장은 FavoritesStore가 처리)
            self.fav_store.touch_last_check(series_url)
            self.refresh_fav_list()
        finally:
            self._auto_thread = None
            self._auto_run_next()

    # ================== 레거시 마이그레이션 ==================
    def _migrate_legacy_favorites(self):
        import json
        from pathlib import Path

        hist_path = Path("urlhistory.json")
        if not hist_path.exists():
            return
        try:
            data = json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception:
            return

        candidates = set()
        if isinstance(data, dict):
            fav_block = data.get("favorites") or data.get("bookmarks")
            if isinstance(fav_block, dict):
                for u in fav_block.keys():
                    if isinstance(u, str) and "/series/" in u:
                        candidates.add(u)
            hist = data.get("history")
            if isinstance(hist, list):
                for x in hist:
                    if isinstance(x, dict) and (x.get("favorite") or x.get("starred")):
                        u = x.get("url") or x.get("link") or x.get("href")
                        if isinstance(u, str) and "/series/" in u:
                            candidates.add(u)
        elif isinstance(data, list):
            for x in data:
                if isinstance(x, dict) and (x.get("favorite") or x.get("starred")):
                    u = x.get("url") or x.get("link") or x.get("href")
                    if isinstance(u, str) and "/series/" in u:
                        candidates.add(u)

        added = 0
        for u in sorted(candidates):
            if not self.fav_store.exists(u):
                self.fav_store.add(u)
                added += 1
        if added:
            self.append_log(f"[즐겨찾기] 레거시에서 {added}개 가져옴")

    # ================== SetupThread 콜백 ==================
    def _print_vpn_banner(self):
        bar = self.LOG_RULE
        self.append_log(bar)
        self.append_log("📢 [안내] TVer는 일본 지역 제한이 있습니다.")
        self.append_log("📢 원활한 다운로드를 위해 반드시 일본 VPN을 켜고 사용해주세요.")
        self.append_log(bar)

    def on_setup_finished(self, ok: bool, ytdlp_path: str, ffmpeg_path: str):
        if not ok:
            self.append_log("[오류] 초기 준비 실패: yt-dlp/ffmpeg를 준비하지 못했습니다.")
            QMessageBox.critical(self, "오류", "초기 준비에 실패했습니다. 로그를 확인하세요.")
            return
        self.ytdlp_exe_path = ytdlp_path
        self.ffmpeg_exe_path = ffmpeg_path
        self.env_ready = True
        self._set_input_enabled(True)

        # VPN 배너 + 완료 고지
        self._print_vpn_banner()
        self.append_log("환경 설정 완료. 다운로드를 시작할 수 있습니다.")

        # 즐겨찾기 자동 확인
        self._auto_check_favorites_on_start()

    # ================== 기타/삭제 유틸 ==================
    def _maybe_update_notice(self):
        try:
            from src.updater import maybe_show_update
            maybe_show_update(self)
        except Exception:
            pass

    def _queue_index(self, url: str) -> int:
        for i, t in enumerate(self.task_queue):
            if t.get('url') == url:
                return i
        return -1

    def _remove_item_from_list(self, url: str):
        for row in range(self.download_list.count()):
            it = self.download_list.item(row)
            w = self.download_list.itemWidget(it)
            if getattr(w, "url", None) == url:
                self.download_list.takeItem(row)
                try:
                    w.deleteLater()
                except Exception:
                    pass
                break
        if url in self.active_urls:
            self.active_urls.discard(url)
        self._update_queue_counter()

    def _remove_from_queue(self, url: str):
        idx = self._queue_index(url)
        if idx == -1:
            return
        self.task_queue.pop(idx)
        self._remove_item_from_list(url)
        self.append_log(f"[대기열] 제거: {url}")
        self.check_queue_and_start()


if __name__ == "__main__":
    sys.excepthook = handle_exception
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r')

    app = QApplication(sys.argv)
    # 내부 명칭은 한글
    app.setApplicationName(APP_NAME_KO)
    # 참고: AboutDialog는 직접 전달하는 APP_VERSION을 사용하므로 아래는 표기용
    app.setApplicationVersion(APP_VERSION)

    app.setStyle("")
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
