import sys, os
from html import escape
from typing import List, Dict
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QSystemTrayIcon, QFileDialog, QWidget,
                             QAbstractSpinBox, QLineEdit, QMenu, QTextEdit, QComboBox)
from PyQt6.QtCore import Qt, QEvent, QObject, QTimer, QLocale, QTranslator, QLibraryInfo
from PyQt6.QtGui import QCursor, QGuiApplication, QFontDatabase, QFont, QKeySequence, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src import autostart, self_update, shortcuts
from src.utils import (load_config, save_config, handle_exception,
                       retired_option_notes,
                       localized_app_name, get_resource_path,
                       canonicalize_config_fragments)
from src.qss import build_qss, palette, UI_FONT_FALLBACKS
from src.icons import is_monochrome_white, tint_icon
from src.message import confirm
from src.about_dialog import AboutDialog
from src.dialogs import SettingsDialog
from src.series_dialog import SeriesSelectionDialog
from src.history_store import HistoryStore
from src.favorites_store import FavoritesStore
from src.queue_store import QueueStore
from src.widgets import (DownloadItemWidget, apply_popup_shape,
                         apply_combo_popup_shape, flatten_combo_popup_margins,
                         COMBO_POPUP_OBJECT)
from src.updater import maybe_show_update
from src.threads.setup_thread import SetupThread
from src.threads.region_thread import (RegionCheckThread, JAPAN_CODE, country_name,
                                       STOP_WAIT_MS as REGION_STOP_WAIT_MS)
from src.ui.main_window_ui import MainWindowUI
from src.series_parser import SeriesParser
from src.download_manager import DownloadManager
from src.controllers.download_list import DownloadListController
from src.controllers.library import LibraryController
from src.tray_controller import TrayController
from src.input_sources import InputSources
from versioninfo import APP_VERSION

SOCKET_NAME = "TVerDownloader_IPC_Socket"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{localized_app_name()} v{APP_VERSION}")
        self.force_quit = False; self.env_ready = False; self.config = load_config()
        self_update.cleanup_workspace()
        self._shortcuts: List[QShortcut] = []; self._guarded_shortcuts: List[QShortcut] = []
        self.setAcceptDrops(True)
        self.history_store = HistoryStore(); self.history_store.load(); self.fav_store = FavoritesStore("favorites.json"); self.fav_store.load()
        self.queue_store = QueueStore(); self._queue_file_ok = self.queue_store.load()
        self.ui = MainWindowUI(self); self.ui.setup_ui(); self.tray_icon = QSystemTrayIcon(self); self.ui.setup_tray(APP_VERSION)
        self.series_parser = SeriesParser(ytdlp_path="", config=self.config)
        self.download_manager = DownloadManager(self.config, self.history_store, self.queue_store)
        self.download_list = DownloadListController(self)
        self.library = LibraryController(self)
        self.tray = TrayController(self)
        self.input_sources = InputSources(self)
        self._connect_signals(); self._set_input_enabled(False)
        self.apply_theme(self.config.get("theme", "light"), persist=False)
        self.set_always_on_top(self.config.get("always_on_top", False), init=True)
        self.ui.set_log_visible(self.config.get("log_visible", True))
        self._apply_initial_geometry()
        self.input_sources.apply_clipboard_watch(self.config.get("clipboard_watch", True))
        self.library.refresh_history_list(); self.library.refresh_fav_list()
        self.apply_shortcuts()
        QApplication.instance().focusChanged.connect(self._sync_shortcut_guard)
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")
        for note in retired_option_notes(self.config):
            self.append_log(note)
        self._start_region_check()
        self.setup_thread = SetupThread(self); self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self._on_setup_finished); self.setup_thread.start()

    def open_settings(self):
        """설정 창을 연다. 메인 창이 트레이에 들어가 있어도 뜬다.

        자리 잡는 일을 exec() 전에 할 수는 없다 - 그 시점에는 창이 아직 만들어지지
        않았다. 0ms 타이머로 exec()가 돌리는 이벤트 루프 안으로 미룬다.
        """
        dialog = SettingsDialog(self.config, self)
        QTimer.singleShot(0, lambda: self._place_dialog(dialog))
        if dialog.exec():
            self.config = load_config()
            self.download_manager.update_config(self.config)
            self.series_parser.update_config(self.config)
            self.input_sources.apply_clipboard_watch(self.config.get("clipboard_watch", True))
            self.apply_shortcuts()
            parallel = self.config["max_concurrent_downloads"]
            fragments = canonicalize_config_fragments(self.config)
            self.append_log(f"설정이 저장되었습니다. 동시 다운로드 개수 {parallel}개"
                            f" / 조각 수 {fragments}개")
            self.library.refresh_history_list()
            self.library.refresh_fav_list()

    def apply_theme(self, theme: str, persist: bool = True):
        """QSS와 아이콘 색을 한 번에 새 테마로 맞춘다."""
        self.config["theme"] = theme
        if persist:
            save_config(self.config)
        app = QApplication.instance()
        app.setStyleSheet(build_qss(theme))
        tinter = getattr(app, "_menu_icon_tinter", None)
        if tinter is not None:
            tinter.set_color(palette(theme)["text"])
        self.ui.apply_theme(theme)
        for list_widget in (self.ui.download_list, self.ui.history_list, self.ui.fav_list):
            for i in range(list_widget.count()):
                widget = list_widget.itemWidget(list_widget.item(i))
                if hasattr(widget, "apply_theme"):
                    widget.apply_theme(theme)

    def toggle_log_panel(self):
        """로그 패널을 접거나 펴고 그 선택을 설정에 남긴다."""
        visible = not self.ui.is_log_visible()
        self.ui.set_log_visible(visible)
        self.config["log_visible"] = visible
        save_config(self.config)

    def toggle_theme(self):
        new_theme = "dark" if self.config.get("theme", "light") == "light" else "light"
        self.apply_theme(new_theme)

    TEXT_ENTRY_TYPES = (QLineEdit, QTextEdit, QAbstractSpinBox)
    """글자를 입력받는 위젯들. 이 중 하나에 포커스가 있으면 '입력 중'으로 본다."""

    LOG_RULE_MAX = 12
    """구분선 한쪽에 넣을 괘선의 최대 개수. 끝까지 채우면 짧은 제목이 괘선에 묻힌다."""

    def apply_shortcuts(self):
        """설정에 저장된 조합으로 단축키를 처음부터 다시 만든다.

        setKey로 갈아끼우지 않는 것은, 조합이 비면 QShortcut 자체를 두지 않아야
        '사용 안 함'이 확실해지고 범위에 따라 만들 개수까지 달라지기 때문이다.
        """
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._shortcuts.clear(); self._guarded_shortcuts.clear()
        targets = {
            shortcuts.WINDOW: (self,),
            shortcuts.DOWNLOAD_LIST: (self.ui.download_list,),
            shortcuts.SEARCH_INPUT: (self.ui.history_search_input, self.ui.fav_search_input),
        }
        table = shortcuts.resolve(self.config)
        for definition in shortcuts.SHORTCUT_DEFS:
            text = table.get(definition.key, "")
            if not text:
                continue
            window_scope = definition.scope == shortcuts.WINDOW
            for widget in targets[definition.scope]:
                handler = self._shortcut_handler(definition.key, widget)
                if handler is None:
                    continue
                shortcut = QShortcut(QKeySequence(text), widget)
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut if window_scope
                                    else Qt.ShortcutContext.WidgetWithChildrenShortcut)
                shortcut.activated.connect(handler)
                self._shortcuts.append(shortcut)
                if window_scope and shortcuts.needs_typing_guard(text):
                    self._guarded_shortcuts.append(shortcut)
        self.ui.apply_shortcut_hints(table)
        self._sync_shortcut_guard(None, QApplication.focusWidget())

    def _shortcut_handler(self, key: str, widget):
        """단축키 하나가 부를 함수. 검색어 지우기는 탭마다 대상 입력칸이 달라 닫아 넣는다."""
        handlers = {
            "open_settings": self.open_settings,
            "toggle_log": self.toggle_log_panel,
            "delete_selected": self.download_list.delete_selected,
            "clear_search": lambda: widget.clear(),
        }
        return handlers.get(key)

    def _sync_shortcut_guard(self, _old=None, new=None):
        """글자를 입력하는 중에는 수식키 없는 창 단축키를 꺼 둔다.

        QShortcut은 켜져 있는 한 키를 위젯보다 먼저 가져가, 콜백에서 되돌아 나와도 이미
        삼킨 키는 입력칸에 닿지 않는다. 범위가 위젯인 것(검색칸 Esc)은 손대지 않는다.
        """
        typing = isinstance(new, self.TEXT_ENTRY_TYPES)
        for shortcut in self._guarded_shortcuts:
            shortcut.setEnabled(not typing)

    def dragEnterEvent(self, event):
        """Qt가 창에만 보내는 이벤트라 여기서 받아 input_sources로 넘긴다."""
        if self.input_sources.urls_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """dragEnter에서 받아 놓고도 이걸 빼면 커서가 금지 표시로 바뀐다."""
        if self.input_sources.urls_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = self.input_sources.urls_from_mime(event.mimeData())
        if not urls:
            event.ignore(); return
        event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        self.input_sources.accept_dropped_urls(urls)

    def _connect_signals(self):
        self.ui.add_button.clicked.connect(self.input_sources.process_input_url); self.ui.url_input.returnPressed.connect(self.input_sources.process_input_url)
        self.ui.bulk_button.clicked.connect(lambda: self.input_sources.open_bulk_add()); self.ui.settings_button.clicked.connect(self.open_settings)
        self.ui.about_button.clicked.connect(
            lambda: AboutDialog(APP_VERSION, self, self.config.get("theme", "light")).exec())
        self.ui.clear_log_button.clicked.connect(self.clear_log); self.ui.on_top_btn.toggled.connect(self.set_always_on_top)
        self.ui.theme_button.clicked.connect(self.toggle_theme)
        self.ui.log_toggle_btn.clicked.connect(self.toggle_log_panel)
        self.ui.clear_completed_button.clicked.connect(self.download_list.clear_completed)
        self.ui.queue_start_button.clicked.connect(self.start_restored_queue)
        self.ui.cancel_selected_button.clicked.connect(self.download_list.cancel_selected)
        self.ui.download_list.itemSelectionChanged.connect(self.download_list.sync_cancel_button)
        self.ui.download_list.customContextMenuRequested.connect(self.download_list.show_context_menu)
        for list_widget in (self.ui.download_list, self.ui.history_list, self.ui.fav_list):
            list_widget.itemSelectionChanged.connect(
                lambda lw=list_widget: self.download_list.sync_selection_styles(lw))
        self.ui.history_list.customContextMenuRequested.connect(self.library.show_history_menu)
        self.ui.history_del_btn.clicked.connect(self.library.remove_selected_history)
        self.ui.history_search_input.textChanged.connect(self.library.refresh_history_list)
        self.ui.fav_search_input.textChanged.connect(self.library.refresh_fav_list)
        self.ui.history_sort_combo.currentIndexChanged.connect(self.library.refresh_history_list)
        self.ui.fav_add_btn.clicked.connect(self.library.add_favorite); self.ui.fav_del_btn.clicked.connect(self.library.remove_selected_favorite)
        self.ui.fav_chk_btn.clicked.connect(self.library.check_all_favorites); self.ui.fav_list.customContextMenuRequested.connect(self.library.show_fav_menu)
        self.download_manager.log.connect(self.append_log); self.download_manager.item_added.connect(self.download_list.add_item_widget)
        self.download_manager.heading.connect(self.append_heading)
        self.download_manager.progress_updated.connect(self.download_list.update_item_widget); self.download_manager.task_finished.connect(self._on_task_finished)
        self.download_manager.queue_changed.connect(self.tray.on_queue_changed)
        self.download_manager.queue_changed.connect(lambda *_: self._sync_queue_start_button())
        self.download_manager.progress_updated.connect(lambda *_: self.tray.refresh_status())
        self.download_manager.all_tasks_completed.connect(self.tray.notify_all_finished)
        self.series_parser.log.connect(lambda ctx, msg: self.append_log(msg)); self.series_parser.finished.connect(self._on_series_parsed)
        self.tray_icon.activated.connect(self.tray.on_activated)

    def set_always_on_top(self, on: bool, init: bool = False):
        """항상 위 설정을 켜고 끈다.

        Windows에서는 플래그를 바꾸면 창이 숨겨져 다시 show()를 불러야 한다. 보이는지는
        바꾸기 전에 봐 둔다 - 뒤에 물으면 '안 떠 있었다'가 되어 트레이 시작에서 창이 뜬다.
        """
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if was_visible or not init:
            self.show()
        if not init: self.config["always_on_top"] = on; save_config(self.config)
        self.ui.on_top_btn.setChecked(on); self.ui.update_pin_button(on)

    def _handle_new_instance(self):
        server = self.sender()
        if isinstance(server, QLocalServer): server.nextPendingConnection().close()
        self.bring_to_front()

    @staticmethod
    def _pull_to_front(window):
        """창을 다른 앱 앞으로 끌어낸다."""
        window.raise_()
        window.activateWindow()

    def _place_dialog(self, dialog):
        """대화상자를 앞으로 끌어내고, 메인 창이 트레이에 있으면 화면 가운데로 옮긴다.

        대화상자에는 작업 표시줄 단추가 없어 뒤에 깔리면 되찾기 어렵다. Qt는 부모 가운데에
        놓는데 최소화된 부모로는 그 계산이 되지 않아 왼쪽 위 구석(0, 30)에 붙는다.
        """
        self._pull_to_front(dialog)
        if self.isVisible() and not self.isMinimized():
            return
        self._center_on_cursor_screen(dialog)

    def _apply_initial_geometry(self):
        """첫 창의 크기와 자리를 우리가 정한다.

        정해 두지 않으면 `--tray` 자동 실행처럼 화면 구성이 확정되기 전에 뜰 때 좌측 위
        구석에 작은 창으로 떨어진다. 최소 폭은 로그를 편 쪽이 커서 set_log_visible 뒤에 부른다.
        """
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.resize(
                max(self.minimumWidth(), min(self.ui.DEFAULT_WIDTH, area.width())),
                max(self.minimumHeight(), min(self.ui.DEFAULT_HEIGHT, area.height())))
        self._center_on_cursor_screen(self)

    @staticmethod
    def _center_on_cursor_screen(window):
        """작업 표시줄을 뺀 영역 안에서 가운데로 옮긴다. 마우스가 있는 화면을 고른다."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = window.frameGeometry()
        frame.moveCenter(area.center())
        x = min(max(frame.x(), area.x()), max(area.x(), area.right() - frame.width() + 1))
        y = min(max(frame.y(), area.y()), max(area.y(), area.bottom() - frame.height() + 1))
        window.move(x, y)

    def bring_to_front(self):
        if self.isMinimized(): self.showNormal()
        elif not self.isVisible(): self.show()
        self.raise_(); self.activateWindow()

    def _set_input_enabled(self, enabled: bool):
        self.ui.url_input.setEnabled(enabled); self.ui.add_button.setEnabled(enabled)
        self.ui.bulk_button.setEnabled(enabled); self.ui.fav_chk_btn.setEnabled(enabled)
        self.ui.set_primary_action_enabled(enabled)

    def _ensure_download_folder(self) -> bool:
        folder = self.config.get("download_folder")
        if folder and os.path.isdir(folder): return True
        new_folder = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택")
        if new_folder: self.config["download_folder"] = new_folder; save_config(self.config); self.download_manager.update_config(self.config); self.append_log(f"다운로드 폴더가 '{new_folder}'(으)로 설정되었습니다."); return True
        return False

    def _request_add_task(self, url: str, title: str = "", thumbnail: str = "") -> bool:
        """대기열에 넣기 전에 이미 받은 것인지 물어본다.

        제목·표지 그림을 아는 자리(시리즈 선택, 즐겨찾기 확인)는 함께 넘긴다. 대기 카드가
        그 자리에서 채워져 차례를 기다리는 동안 다시 물어보러 갈 일이 없다.
        """
        if self.history_store.exists(url):
            again = confirm(self, "중복 다운로드",
                            f"이미 다운로드한 항목입니다:\n\n{self.history_store.get_title(url)}\n\n다시 다운로드할까요?",
                            icon_name="download", theme=self.config.get("theme", "light"))
            if not again: self.append_log(f"[알림] 중복 다운로드 취소: {url}"); return False
        return self.download_manager.add_task(url, title=title, thumbnail=thumbnail)

    def _on_setup_finished(self, ok: bool, ytdlp_path: str, ffmpeg_path: str):
        """준비가 끝났음을 알리고 대기열을 되살린다.

        **'다운로드를 시작할 수 있습니다'를 덧붙이지 않는다** - 바로 위 지역 안내가 VPN이
        없어 받을 수 없다고 말한 뒤라, 준비된 것은 프로그램이라는 뜻이 반대로 읽힌다.
        """
        if not ok: self.append_log("[오류] 초기 준비 실패: yt-dlp/ffmpeg를 준비하지 못했습니다."); QMessageBox.critical(self, "오류", "초기 준비에 실패했습니다. 로그를 확인하세요."); return
        self.download_manager.set_paths(ytdlp_path, ffmpeg_path); self.series_parser.set_ytdlp_path(ytdlp_path); self.env_ready = True
        self._set_input_enabled(True)
        self._show_region_notice()
        self.append_log("환경 설정 완료.")
        self._restore_queue()
        if self.config.get("auto_update_check", True):
            QTimer.singleShot(1000, self._check_for_update)
        if self.config.get("auto_check_favorites_on_start", False):
            QTimer.singleShot(2500, self.library.check_all_favorites)

    def _restore_queue(self):
        """지난 실행에서 끝내지 못한 대기열을 목록에 되살린다.

        준비가 끝난 뒤에 부르는 것은 되살린 항목도 제목을 물어보러 갈 수 있어야 해서다.
        되살리기만 하고 받기 시작하지는 않는다 - 이유는 restore_task에 적어 두었다.
        """
        if not self._queue_file_ok:
            self.append_log("[알림] 대기열 파일이 손상되어 읽지 못했습니다. 빈 대기열로 시작합니다.")
        entries = self.queue_store.entries()
        if not entries:
            return
        restored = sum(1 for entry in entries
                       if self.download_manager.restore_task(entry.get("url", ""),
                                                             title=entry.get("title", ""),
                                                             thumbnail=entry.get("thumbnail", "")))
        if restored:
            self.append_log(f"[대기열] 지난 실행에서 남은 {restored}개를 되살렸습니다. "
                            "'대기열 시작'을 누르면 받기 시작합니다.")

    def _sync_queue_start_button(self):
        """되살린 항목이 남아 있는 동안에만 `대기열 시작`을 보인다."""
        self.ui.set_queue_start_visible(self.download_manager.held_count() > 0)

    def start_restored_queue(self):
        """되살린 대기 항목을 지금부터 받는다. 폴더가 없으면 전부 오류 카드가 되어 먼저 본다."""
        if not self.download_manager.held_count():
            return
        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 설정되지 않아 대기열을 시작하지 못했습니다.")
            return
        started = self.download_manager.start_held_tasks()
        self.append_log(f"[대기열] 되살린 {started}개를 대기열에 넣었습니다.")

    def _check_for_update(self):
        """새 버전을 확인한다. 개수는 download_manager가 센다 - 직접 세면 변환만 남은 것을 빠뜨린다."""
        maybe_show_update(self, APP_VERSION, self.append_log,
                          pending_downloads=self.download_manager.pending_count())

    def _add_from_selection(self, episode_info: List[Dict[str, str]], label: str):
        """에피소드 선택 창을 띄우고 고른 것만 대기열에 넣는다. 제목·표지 그림도 함께 넘긴다."""
        dialog = SeriesSelectionDialog(episode_info, self)
        if not dialog.exec():
            self.append_log(f"{label} 에피소드 추가를 취소했습니다.")
            return
        selected_urls = dialog.get_selected_urls()
        if not selected_urls:
            self.append_log(f"{label} 선택된 에피소드가 없어 추가하지 않았습니다.")
            return
        known = {ep.get("url"): ep for ep in episode_info if ep.get("url")}
        added_count = 0
        for url in selected_urls:
            episode = known.get(url) or {}
            if self._request_add_task(url, title=episode.get("title", ""),
                                      thumbnail=episode.get("thumbnail_url", "")):
                added_count += 1
        self.append_log(f"{label} 선택한 {added_count}개 에피소드를 추가했습니다.")

    def _on_series_parsed(self, context: str, series_url: str, series_title: str, episode_info: List[Dict[str, str]]):
        """분석이 끝난 시리즈를 요청 맥락에 맞게 보낸다. 즐겨찾기 두 갈래는 library가 맡는다."""
        if context in ('single', 'bulk'):
            if not episode_info: self.append_log(f"[{context}] '{series_url}' 시리즈에서 에피소드를 찾지 못했습니다."); return
            self._add_from_selection(episode_info, f"[{context}] 시리즈에서")

        elif context == 'fav-check':
            self.library.on_fav_check_parsed(series_url, series_title, episode_info)

        elif context == 'fav-add-check':
            self.library.on_fav_add_check_parsed(series_url, series_title)

    def _on_task_finished(self, url: str, success: bool, final_filepath: str, meta: dict):
        widget = self.download_list.find_item_widget(url)
        if not widget or not isinstance(widget, DownloadItemWidget): return
        if success and final_filepath:
            title = meta.get('title', widget.title_label.text())
            series_id = meta.get('series_id'); thumbnail_url = meta.get('thumbnail')
            self.history_store.add(url, title, final_filepath, series_id=series_id, thumbnail_url=thumbnail_url)
            self.history_store.save(); self.library.refresh_history_list()

    def _start_region_check(self):
        """지금 IP가 일본인지 물어보러 보낸다. 준비를 기다리지 않는 것은 yt-dlp와 무관해서다.

        **끄는 설정을 두지 않는다** - VPN을 켰는지는 TVer에서 무엇을 하든 먼저 알아야 할
        것이라 고를 일이 아니다. 스레드에 부모를 주지 않으므로 이 참조를 놓으면 도는 채로
        파괴된다. 끝까지 들고 있는다.
        """
        self._region_code = ""
        self._region_failed = False
        self._region_notice_shown = False
        self.region_thread = RegionCheckThread()
        self.region_thread.resolved.connect(self._on_region_resolved)
        self.region_thread.failed.connect(self._on_region_failed)
        self.region_thread.start()

    def _on_region_resolved(self, country_code: str):
        """알아낸 국가를 적어 둔다. 알릴지는 준비가 끝났는지에 달렸다."""
        self._region_code = country_code
        self._show_region_notice()

    def _on_region_failed(self):
        """못 물어봤다고 적어 둔다. 이때는 나라를 모르므로 예전의 일반 안내로 돌아간다."""
        self._region_failed = True
        self._show_region_notice()

    REGION_FALLBACK_LINES = ["IP 확인이 실패했습니다.",
                             "TVer는 일본 지역 제한이 있습니다.",
                             "원활한 다운로드를 위해 일본 VPN을 켜고 사용해주세요."]
    """확인하지 못했을 때 내보내는 안내. 나라를 모르니 무엇을 하라고만 말한다.

    **여기서 조용히 넘어가면 안 된다** - 확인이 실패하는 상황은 대개 통신이 이상할 때라,
    VPN이 꺼져 있을 법한 자리이기도 하다. 모른다는 사실을 밝히고 예전 안내를 그대로 준다.
    """

    def _show_region_notice(self):
        """지역 안내를 로그 맨 아래에 한 번만 붙인다. 알리기만 하고 아무것도 막지 않는다.

        준비가 끝난 뒤로 미루는 것은 yt-dlp·FFmpeg 확인 줄 사이에 끼면 읽는 차례가 끊기기
        때문이다. 답이 온 것과 준비가 끝난 것 중 늦게 오는 쪽이 이 함수를 부른다.
        **IP는 어디에도 적지 않는다** - 로그를 그대로 붙여 도움을 청하는 자리가 있다.
        """
        if self._region_notice_shown or not self.env_ready:
            return
        if self._region_code == JAPAN_CODE:
            lines = ["현재 일본 IP 입니다. 원활한 다운로드가 가능합니다."]
            color_key = "log_success"
        elif self._region_code:
            lines = ["현재 일본 IP가 아닙니다.",
                     f"{country_name(self._region_code)} 국가이므로 VPN을 켜주세요.",
                     "TVer는 일본 지역 제한이 있어 VPN 없이는 받을 수 없습니다."]
            color_key = "notice"
        elif self._region_failed:
            lines = list(self.REGION_FALLBACK_LINES)
            color_key = "notice"
        else:
            return
        self._region_notice_shown = True
        self.append_notice("안내", lines, color_key=color_key)

    def stop_region_check(self):
        """지역 확인을 거둔다. 아직 답을 기다리는 중이면 그 답을 버리고 그냥 끝낸다.

        오래 기다리지 않는 것은 DNS가 막힌 회선에서 십수 초가 걸리기 때문이다 - 부모 없는
        스레드라 도는 채로 두어도 프로세스가 그대로 끝난다.
        """
        thread = self.region_thread
        if thread is None:
            return
        thread.stop()
        thread.wait(REGION_STOP_WAIT_MS)

    def append_log(self, text: str):
        """로그 한 줄을 기본 글자색으로 붙인다.

        넣을지 말지는 부르는 쪽이 정한다. 여기 쌓을 것은 파일·대기열·네트워크뿐이고, 테마
        전환처럼 누른 결과가 화면에 바로 보이는 조작은 봐야 할 줄만 밀어낸다.

        **글자에서 낱말을 찾아 색을 입히지 않는다.** 예전에는 '완료'·'성공'·'[오류]'가 든
        줄을 칠했는데, 그 낱말은 알릴 것이 없는 줄에도 흔하다 - `ffmpeg.exe 이동 완료`,
        `환경 설정 완료`까지 물들어 정작 색이 붙은 지역 안내가 묻혔다. 색을 쓰는 곳은
        append_notice 하나뿐이다.
        """
        self.ui.log_output.append(text)
        self._scroll_log_to_end()

    def append_heading(self, title: str, body: str):
        """제목을 괘선으로 두르고 그 아래 한 줄을 붙인다. 로그가 길어진 뒤 구간을 찾는 줄이다."""
        self.append_log(f"{self._log_heading(title)}\n{body}")

    def append_notice(self, title: str, lines: List[str], color_key: str = "notice"):
        """가장 중요한 안내를 굵게, 위아래 괘선 사이에 넣는다. 색과 굵기만으로는 묻힌다.

        색을 고를 수 있는 것은 같은 자리에 좋은 소식도 오기 때문이다 - 지역 안내가
        일본이냐 아니냐로 갈리는데, 둘 다 적색이면 어느 쪽인지 읽어야 알게 된다.
        """
        colors = palette(self.config.get("theme", "light"))
        head = self._log_heading(title)
        block = "\n".join([head, *lines, self._rule_matching(head)])
        self.ui.log_output.append(
            f'<span style="color: {colors[color_key]}; font-weight: bold;">'
            f'{self._as_html(block)}</span>')
        self._scroll_log_to_end()

    def _log_text_width(self) -> int:
        """로그 한 줄이 접히지 않고 들어가는 폭.

        위젯이 아니라 고정폭 상수에서 잰다 - 로그를 접은 채로 시작하면 그 자리에 배치가
        돌지 않아 위젯이 창 절반쯤 되는 폭을 들고 있다. 세로 스크롤바 폭은 늘 뺀다.
        """
        log = self.ui.log_output
        frame = log.width() - log.maximumViewportSize().width()
        return int(self.ui.LOG_PANE_WIDTH - frame
                   - 2 * log.document().documentMargin()
                   - log.verticalScrollBar().sizeHint().width())

    def _log_heading(self, title: str) -> str:
        """제목 양옆을 괘선으로 채운 구분선. 로그 폭 안에서 한 줄로 떨어진다.

        개수를 고정하면 긴 제목이 넘친다 - '다운로드 시작'은 양옆 12개에 389px로, 로그 폭
        354px에 들어가지 못하고 두 줄로 접혔다.
        """
        metrics = self.ui.log_output.fontMetrics()
        dash_width = metrics.horizontalAdvance("─") or 1
        available = self._log_text_width() - metrics.horizontalAdvance(f" {title} ")
        count = min(self.LOG_RULE_MAX, max(1, int(available // dash_width) // 2))
        rule = "─" * count
        return f"{rule} {title} {rule}"

    def _rule_matching(self, head: str) -> str:
        """head와 같은 폭으로 보이는 괘선. 괘선은 전각, 제목 양옆 공백은 반각이라 개수로는 어긋난다."""
        metrics = self.ui.log_output.fontMetrics()
        dash_width = metrics.horizontalAdvance("─") or 1
        count = max(1, round(metrics.horizontalAdvance(head) / dash_width))
        return "─" * count

    @staticmethod
    def _as_html(text: str) -> str:
        """로그 한 덩어리를 서식 있는 텍스트로. QTextEdit은 span 안의 줄바꿈을 공백으로 흘린다."""
        return escape(text).replace("\n", "<br>")

    def _scroll_log_to_end(self):
        scrollbar = self.ui.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self): self.ui.log_output.clear()

    def play_file(self, filepath: str):
        try: os.startfile(filepath)
        except Exception as e: self.append_log(f"[오류] 재생 실패: {e}")

    def changeEvent(self, event):
        """Qt가 창에만 보내는 이벤트라 여기서 받아 트레이 쪽으로 넘긴다."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.tray.handle_minimized()

    def closeEvent(self, event):
        """Qt가 창에만 보내는 이벤트라 여기서 받아 트레이 쪽으로 넘긴다."""
        self.tray.handle_close(event)

    def quit_application(self):
        """트레이 메뉴가 부르는 이름. 실제로 멈추는 일은 tray가 맡는다."""
        self.tray.quit_application()

    def set_autostart(self, enabled: bool):
        """시작 프로그램 등록을 켜거나 끈다.

        레지스트리 쓰기가 막히면 체크만 켜진 채 등록되지 않아, 다음 로그인에 안 뜨는 이유를
        알 길이 없다. 표시를 실제 상태로 되돌리고 로그에 남긴다.
        """
        if autostart.set_enabled(enabled):
            self.append_log("[시작 프로그램] 윈도우 시작 시 실행: "
                            + ("켜짐(트레이로 시작)" if enabled else "꺼짐"))
        else:
            self.append_log("[오류] 시작 프로그램 설정을 저장하지 못했습니다.")
        self.ui.sync_autostart_check()

FONT_DIR = Path("assets") / "fonts"
UI_FONT_FILES = [
    FONT_DIR / "PretendardVariable.ttf",
    FONT_DIR / "PretendardJP-Regular.ttf",
]
MONO_FONT_FILES = [FONT_DIR / "JetBrainsMono-Regular.ttf"]

UI_FONT_HINTING = QFont.HintingPreference.PreferNoHinting
UI_FONT_STYLE_STRATEGY = QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality


class FontRenderingGuard(QObject):
    """스타일시트가 새로 만든 폰트에 글자 렌더링 설정을 다시 입힌다.

    QSS에 font 속성이 있으면 Qt가 QFont를 새로 만들고 setFont()의 힌팅·안티앨리어싱이
    따라오지 않는다. 덮이는 시점은 Polish가 아니라 그 뒤의 FontChange라 셋을 모두 본다.
    """

    WATCHED = (QEvent.Type.Polish, QEvent.Type.FontChange, QEvent.Type.StyleChange)

    def eventFilter(self, obj, event):
        if event.type() in self.WATCHED and isinstance(obj, QWidget):
            font = obj.font()
            if (font.hintingPreference() != UI_FONT_HINTING
                    or font.styleStrategy() != UI_FONT_STYLE_STRATEGY):
                font.setHintingPreference(UI_FONT_HINTING)
                font.setStyleStrategy(UI_FONT_STYLE_STRATEGY)
                obj.setFont(font)
        return super().eventFilter(obj, event)


def register_font(path: Path) -> List[str]:
    """서체 파일 하나를 등록하고 패밀리명 목록을 돌려준다. 실패해도 빈 목록으로 돌아간다."""
    try:
        full_path = get_resource_path(path)
        if not full_path.is_file():
            print(f"INFO: 번들 서체를 찾지 못했습니다: {full_path}")
            return []
        font_id = QFontDatabase.addApplicationFont(str(full_path))
        if font_id == -1:
            print(f"WARNING: 서체를 불러오지 못했습니다: {full_path}")
            return []
        return QFontDatabase.applicationFontFamilies(font_id)
    except Exception as e:
        print(f"WARNING: 서체 등록 중 오류가 발생했습니다: {path} - {e}")
        return []


class MenuIconTinter(QObject):
    """메뉴가 열릴 때 흰색 아이콘을 테마 글자색으로 바꿔 놓는다.

    입력칸 우클릭 메뉴는 Qt가 만들고 아이콘도 Qt 것(:/icons)이라 일곱 개가 전부 흰색이고
    라이트 테마에서 묻힌다. 새로 만들지 않는 것은 항목이 켜지고 꺼지는 조건을 그대로 두려는 것.
    """

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color

    def set_color(self, color: str):
        self._color = color

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QMenu):
            self._tint(obj)
        return super().eventFilter(obj, event)

    def _tint(self, menu):
        """메뉴 항목들의 아이콘을 지금 색으로 맞춘다.

        칠하기 전 원본을 들고 있는다. 한 번 칠하면 더는 흰색이 아니라서, 원본 없이는 테마가
        바뀌었을 때 다시 칠할 대상으로 알아보지 못한다.
        """
        for action in menu.actions():
            icon = action.icon()
            if icon.isNull() or action.property("tinted_for") == self._color:
                continue
            source = action.property("untinted_icon")
            if source is None:
                if not is_monochrome_white(icon):
                    continue
                source = icon
                action.setProperty("untinted_icon", source)
            action.setIcon(tint_icon(source, self._color))
            action.setProperty("tinted_for", self._color)


class PopupShapeGuard(QObject):
    """제 창을 가진 팝업(메뉴·콤보 펼침 목록)을 모두 같은 모양으로 맞춘다.

    한 곳에서 거는 것은 콤보박스가 여러 파일에 흩어져 있고, 입력칸 우클릭 메뉴처럼 클래스를
    고를 수 없는 팝업도 있어서다. Show에서 걸면 Qt가 창을 숨겨 메뉴가 뜨지 않아 Polish에서 건다.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Polish:
            if isinstance(obj, QMenu):
                apply_popup_shape(obj)
            elif isinstance(obj, QComboBox):
                apply_combo_popup_shape(obj)
        elif (event.type() == QEvent.Type.Show
              and obj.objectName() == COMBO_POPUP_OBJECT):
            flatten_combo_popup_margins(obj)
        return super().eventFilter(obj, event)


def setup_menu_icons(app: QApplication, theme: str) -> MenuIconTinter:
    """팝업 아이콘 색과 모양을 우리 것에 맞추는 감시자를 앱에 건다."""
    tinter = MenuIconTinter(palette(theme)["text"], app)
    app.installEventFilter(tinter)
    app._menu_icon_tinter = tinter
    shape = PopupShapeGuard(app)
    app.installEventFilter(shape)
    app._menu_shape_guard = shape
    return tinter


def setup_translations(app: QApplication) -> None:
    """Qt 기본 위젯의 문구를 OS 표시 언어로 맞춘다.

    QTranslator를 설치하지 않으면 입력칸 우클릭 메뉴 같은 것이 OS 언어와 무관하게 영어로 나온다.
    """
    try:
        translator = QTranslator(app)
        candidates = [
            str(get_resource_path(Path("translations"))),
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        ]
        for directory in candidates:
            if translator.load(QLocale.system(), "qtbase", "_", directory):
                app.installTranslator(translator)
                return
        print(f"INFO: {QLocale.system().name()} 용 Qt 번역을 찾지 못했습니다. 영어로 표시됩니다.")
    except Exception as e:
        print(f"WARNING: Qt 번역을 불러오지 못했습니다: {e}")


def setup_app_font(app: QApplication) -> None:
    """번들 서체를 등록하고 앱 기본 서체를 지정한다. 실패한 것은 시스템 서체로 폴백한다."""
    families: List[str] = []
    for font_file in UI_FONT_FILES:
        registered = register_font(font_file)
        if registered:
            families.append(registered[0])
    for font_file in MONO_FONT_FILES:
        register_font(font_file)

    if not families:
        print("INFO: 번들 서체를 하나도 등록하지 못했습니다. 시스템 서체를 사용합니다.")

    try:
        font = QFont()
        font.setFamilies(families + list(UI_FONT_FALLBACKS))
        font.setHintingPreference(UI_FONT_HINTING)
        if UI_FONT_STYLE_STRATEGY is not None:
            font.setStyleStrategy(UI_FONT_STYLE_STRATEGY)
        app.setFont(font)
        app._font_guard = FontRenderingGuard(app)
        app.installEventFilter(app._font_guard)
    except Exception as e:
        print(f"WARNING: 기본 서체 지정에 실패했습니다: {e}. Qt 기본값을 사용합니다.")

if __name__ == "__main__":
    sys.excepthook = handle_exception
    app = QApplication(sys.argv)
    config = load_config()
    theme = config.get("theme", "light")
    setup_menu_icons(app, theme)
    setup_translations(app)
    setup_app_font(app)
    app.setStyleSheet(build_qss(theme))
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if socket.waitForConnected(500):
        if not autostart.launched_for_tray():
            socket.writeData(b'show'); socket.flush(); socket.waitForBytesWritten(1000)
        socket.close()
        sys.exit(0)
    else:
        QLocalServer.removeServer(SOCKET_NAME)
        server = QLocalServer()
        server.listen(SOCKET_NAME)
        app.setApplicationName(localized_app_name()); app.setApplicationVersion(APP_VERSION)
        app.setStyle("Fusion")
        window = MainWindow()
        server.newConnection.connect(window._handle_new_instance)
        if not autostart.launched_for_tray():
            window.show()
        sys.exit(app.exec())
