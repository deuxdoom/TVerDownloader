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
        self.input_sources.apply_clipboard_watch(self.config.get("clipboard_watch", False))
        self.library.refresh_history_list(); self.library.refresh_fav_list()
        self.apply_shortcuts()
        QApplication.instance().focusChanged.connect(self._sync_shortcut_guard)
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")
        for note in retired_option_notes(self.config):
            self.append_log(note)
        self.setup_thread = SetupThread(self); self.setup_thread.log.connect(self.append_log)
        self.setup_thread.finished.connect(self._on_setup_finished); self.setup_thread.start()

    def open_settings(self):
        """설정 창을 연다. 메인 창이 트레이에 들어가 있어도 뜬다.

        자리를 잡는 일을 exec() 전에 할 수는 없다. 그 시점에는 창이 아직 만들어지지
        않아 raise_()도 크기 계산도 할 것이 없다. 0ms 타이머로 exec()가 돌리는
        이벤트 루프 안으로 미룬다.
        """
        dialog = SettingsDialog(self.config, self)
        QTimer.singleShot(0, lambda: self._place_dialog(dialog))
        if dialog.exec():
            self.config = load_config()
            self.download_manager.update_config(self.config)
            self.series_parser.update_config(self.config)
            self.input_sources.apply_clipboard_watch(self.config.get("clipboard_watch", False))
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
    """구분선 한쪽에 넣을 괘선의 최대 개수.

    폭이 남는다고 끝까지 채우면 짧은 제목에서 괘선만 늘어져 정작 제목이 묻힌다."""

    def apply_shortcuts(self):
        """설정에 저장된 조합으로 단축키를 처음부터 다시 만든다.

        setKey로 갈아끼우지 않고 버린 뒤 새로 만든다. 조합이 비면 QShortcut 자체를
        두지 않아야 '사용 안 함'이 확실해지고, 범위가 여러 위젯에 걸린 항목은 만들
        개수까지 달라져서 어차피 한 번에 다시 세우는 편이 경로가 하나로 남는다.
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
        """단축키 하나가 부를 함수를 돌려준다.

        검색어 지우기는 탭마다 대상 입력칸이 달라서, 붙은 위젯을 닫아 넣은 함수를
        만든다. 이름을 모르는 항목은 None을 돌려주고 호출부가 건너뛴다.
        """
        handlers = {
            "open_settings": self.open_settings,
            "toggle_log": self.toggle_log_panel,
            "delete_selected": self.download_list.delete_selected,
            "clear_search": lambda: widget.clear(),
        }
        return handlers.get(key)

    def _sync_shortcut_guard(self, _old=None, new=None):
        """글자를 입력하는 중에는 수식키 없는 창 단축키를 꺼 둔다.

        QShortcut은 켜져 있는 한 키를 위젯보다 먼저 가져간다. 콜백 안에서 상황을
        보고 되돌아 나와도 이미 삼킨 키는 입력칸에 도착하지 않으므로, 판단을
        콜백이 아니라 활성 여부로 옮긴다.

        범위가 위젯인 단축키는 손대지 않는다. 검색칸의 Esc처럼 대상이 입력칸
        자신인 경우가 있어서, 입력 중이라고 끄면 있어야 할 자리에서 사라진다.
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

        Windows에서는 창 플래그를 바꾸면 창이 숨겨져서 다시 show()를 불러야 한다.
        다만 아직 한 번도 뜨지 않았을 때는 부르지 않는다. 시작 프로그램으로 켜져
        트레이에만 있어야 할 실행이 이 자리에서 창을 띄워 버린다.

        보이는지는 플래그를 바꾸기 전에 봐 둔다. 바꾸는 순간 창이 숨겨져서, 그
        뒤에 물으면 떠 있던 창까지 '안 떠 있었다'고 나온다.
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
        """대화상자를 앞으로 끌어내고, 메인 창이 없으면 화면 가운데로 옮긴다.

        트레이 메뉴에서 부르면 다른 앱이 앞에 있을 수 있고, 대화상자에는 작업
        표시줄 단추가 없어 뒤에 깔리면 되찾을 방법이 마땅치 않다. 그래서 끌어낸다.

        메인 창이 트레이에 들어가 있으면 자리도 직접 잡는다. Qt는 대화상자를 부모
        가운데에 놓는데, 최소화된 부모로는 그 계산이 되지 않아 화면 왼쪽 위
        구석(0, 30)에 붙어 나온다. 부모가 보이는 동안에는 손대지 않는다 —
        그때는 창 가운데가 눈이 가 있는 자리라 그대로가 낫다.
        """
        self._pull_to_front(dialog)
        if self.isVisible() and not self.isMinimized():
            return
        self._center_on_cursor_screen(dialog)

    def _apply_initial_geometry(self):
        """첫 창의 크기와 자리를 우리가 정한다.

        정해 두지 않으면 배치가 창 관리자에게 넘어간다. 로그인과 함께 뜨는 경우
        (`--tray` 자동 실행) 화면 구성과 배율이 아직 확정되기 전이라, 그 판단이
        좌측 위 구석에 원래보다 작은 창으로 떨어질 때가 있었다. 화면에 맞춰 줄인
        뒤 가운데에 놓으면 무엇이 먼저 준비되든 같은 자리에 같은 크기로 뜬다.

        최소 폭은 로그 패널을 편 상태에서 더 크므로(`set_log_visible`) 그 뒤에 부른다.
        화면이 기본 크기보다 좁아도 최소 크기 아래로는 줄이지 않는다 — 그 아래로는
        카드가 눌려서, 차라리 조금 넘치는 편이 낫다.
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
        """작업 표시줄을 뺀 영역 안에서 가운데로 옮긴다.

        availableGeometry라서 작업 표시줄과 겹치지 않는다. 마우스가 있는 화면을
        고르는 것은 방금 트레이를 누른 자리가 그 화면이기 때문이다. 화면보다 큰
        창이면 가운데 대신 영역 안쪽으로 밀어 넣어, 제목 표시줄이 잘리지 않게 한다.
        """
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

        제목·표지 그림을 아는 자리(시리즈 선택, 즐겨찾기 확인)는 함께 넘긴다.
        받아 둔 것이 있으면 카드가 그 자리에서 채워져, 차례를 기다리는 동안
        다시 물어보러 갈 일이 없다.
        """
        if self.history_store.exists(url):
            again = confirm(self, "중복 다운로드",
                            f"이미 다운로드한 항목입니다:\n\n{self.history_store.get_title(url)}\n\n다시 다운로드할까요?",
                            icon_name="download", theme=self.config.get("theme", "light"))
            if not again: self.append_log(f"[알림] 중복 다운로드 취소: {url}"); return False
        return self.download_manager.add_task(url, title=title, thumbnail=thumbnail)

    def _on_setup_finished(self, ok: bool, ytdlp_path: str, ffmpeg_path: str):
        if not ok: self.append_log("[오류] 초기 준비 실패: yt-dlp/ffmpeg를 준비하지 못했습니다."); QMessageBox.critical(self, "오류", "초기 준비에 실패했습니다. 로그를 확인하세요."); return
        self.download_manager.set_paths(ytdlp_path, ffmpeg_path); self.series_parser.set_ytdlp_path(ytdlp_path); self.env_ready = True
        self._set_input_enabled(True)
        self.append_notice("안내", ["TVer는 일본 지역 제한이 있습니다.",
                                    "원활한 다운로드를 위해 일본 VPN을 켜고 사용해주세요."])
        self.append_log("환경 설정 완료. 다운로드를 시작할 수 있습니다.")
        self._restore_queue()
        if self.config.get("auto_update_check", True):
            QTimer.singleShot(1000, self._check_for_update)
        if self.config.get("auto_check_favorites_on_start", True):
            QTimer.singleShot(2500, self.library.check_all_favorites)

    def _restore_queue(self):
        """지난 실행에서 끝내지 못한 대기열을 목록에 되살린다.

        부르는 자리가 준비가 끝난 뒤인 것은 되살린 항목도 제목을 물어보러 갈 수
        있어야 해서다. 미리 묻기는 yt-dlp 경로가 정해지기 전에는 줄만 서 있는다.

        **되살리기만 하고 받기 시작하지는 않는다.** 이유는 restore_task에 적어
        두었다 — 시작 프로그램으로 뜨면 VPN보다 앱이 먼저 서서, 그 자리에서
        받기 시작하면 담아 둔 것이 전부 지역 제한에 걸린다.
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
        """되살린 대기 항목을 지금부터 받기 시작한다.

        폴더를 먼저 확인하는 것은 재다운로드와 같은 이유다. 폴더가 없으면
        항목마다 곧바로 실패로 떨어져, 되살린 것이 한꺼번에 오류 카드가 된다.
        """
        if not self.download_manager.held_count():
            return
        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 설정되지 않아 대기열을 시작하지 못했습니다.")
            return
        started = self.download_manager.start_held_tasks()
        self.append_log(f"[대기열] 되살린 {started}개를 대기열에 넣었습니다.")

    def _check_for_update(self):
        """새 버전을 확인한다. 받는 중인 것이 있으면 업데이트 쪽이 먼저 물어본다.

        개수를 세는 일은 download_manager가 한다. 창에서 자료구조를 직접 세면
        변환만 남은 항목을 빠뜨린다.
        """
        maybe_show_update(self, APP_VERSION, self.append_log,
                          pending_downloads=self.download_manager.pending_count())

    def _add_from_selection(self, episode_info: List[Dict[str, str]], label: str):
        """에피소드 선택 창을 띄우고, 고른 것만 대기열에 넣는다.

        분석이 제목과 표지 그림을 이미 들고 왔으므로 주소와 함께 넘긴다. 대기
        카드가 그 자리에서 채워지고, 미리 물어보러 갈 일도 그만큼 줄어든다.
        """
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
        """분석이 끝난 시리즈를 요청 맥락에 맞게 처리한다.

        맥락을 갈라 보내기만 한다. 즐겨찾기 쪽 두 갈래는 목록을 다시 그리고
        기록과 대조하는 일이라 library가 맡는다.
        """
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

    def append_log(self, text: str):
        """로그 한 줄을 붙인다.

        넣을지 말지는 부르는 쪽이 정한다. 여기에 쌓을 것은 나중에 다시 보면서
        무슨 일이 있었는지 따져볼 만한 것뿐이다. 파일·대기열·네트워크가 그쪽이고,
        테마 전환이나 패널 접기처럼 누른 결과가 화면에 바로 보이는 조작은 적어 두어도
        다시 읽을 일이 없으면서 정작 봐야 할 줄만 밀어낸다.
        """
        colors = palette(self.config.get("theme", "light"))
        color_map = {
            "[오류]": colors["danger"], "[치명적 오류]": colors["danger"],
            "완료": colors["log_success"], "성공": colors["log_success"],
        }
        color = next((c for k, c in color_map.items() if k in text), None)
        if color:
            self.ui.log_output.append(
                f'<span style="color: {color};">{self._as_html(text)}</span>')
        else:
            self.ui.log_output.append(text)
        self._scroll_log_to_end()

    def append_heading(self, title: str, body: str):
        """제목을 괘선으로 두르고 그 아래에 한 줄을 붙인다.

        다운로드가 시작될 때처럼 로그가 길어진 뒤에도 구간을 눈으로 찾기 위한 줄이다.
        """
        self.append_log(f"{self._log_heading(title)}\n{body}")

    def append_notice(self, title: str, lines: List[str]):
        """가장 중요한 안내를 굵은 적색으로, 위아래 괘선 사이에 넣어 출력한다.

        색과 굵기만으로는 뒤이어 쌓이는 로그에 묻히기 쉬워서 블록을 괘선으로 닫는다.
        """
        colors = palette(self.config.get("theme", "light"))
        head = self._log_heading(title)
        block = "\n".join([head, *lines, self._rule_matching(head)])
        self.ui.log_output.append(
            f'<span style="color: {colors["notice"]}; font-weight: bold;">'
            f'{self._as_html(block)}</span>')
        self._scroll_log_to_end()

    def _log_text_width(self) -> int:
        """로그 한 줄이 접히지 않고 들어가는 폭.

        폭의 근거를 위젯이 아니라 고정폭 상수에서 가져온다. 로그 패널을 접은 채로
        시작하면 그 자리에 배치가 한 번도 돌지 않아 위젯이 창 절반쯤 되는 폭을 들고
        있고, 그 값으로 괘선을 뽑으면 패널을 펴는 순간 줄이 접힌다.

        세로 스크롤바 폭은 지금 떠 있지 않아도 미리 뺀다. 로그가 쌓여 스크롤바가
        생기면 그만큼 좁아지면서 이미 찍혀 있던 줄까지 다시 접힌다.
        """
        log = self.ui.log_output
        frame = log.width() - log.maximumViewportSize().width()
        return int(self.ui.LOG_PANE_WIDTH - frame
                   - 2 * log.document().documentMargin()
                   - log.verticalScrollBar().sizeHint().width())

    def _log_heading(self, title: str) -> str:
        """제목 양옆을 괘선으로 채운 구분선. 로그 폭 안에서 한 줄로 떨어진다.

        개수를 고정해 두면 제목이 긴 쪽이 넘친다. '다운로드 시작'은 양옆 12개일 때
        389px이라 354px짜리 로그 폭에 들어가지 못하고 두 줄로 접혔다. 제목이 차지하는
        폭도 글꼴을 재야 아는 값이라, 제목이 쓰고 남은 폭을 양쪽이 반씩 나눠 갖는다.
        """
        metrics = self.ui.log_output.fontMetrics()
        dash_width = metrics.horizontalAdvance("─") or 1
        available = self._log_text_width() - metrics.horizontalAdvance(f" {title} ")
        count = min(self.LOG_RULE_MAX, max(1, int(available // dash_width) // 2))
        rule = "─" * count
        return f"{rule} {title} {rule}"

    def _rule_matching(self, head: str) -> str:
        """head와 같은 폭으로 보이는 괘선을 만든다.

        글자 수로 세면 어긋난다. 괘선은 전각이고 제목 양옆 공백은 반각이라,
        같은 개수를 찍으면 닫는 줄이 여는 줄보다 넓어진다.
        """
        metrics = self.ui.log_output.fontMetrics()
        dash_width = metrics.horizontalAdvance("─") or 1
        count = max(1, round(metrics.horizontalAdvance(head) / dash_width))
        return "─" * count

    @staticmethod
    def _as_html(text: str) -> str:
        """로그 한 덩어리를 서식 있는 텍스트로 바꾼다.

        QTextEdit은 span 안의 줄바꿈 문자를 그냥 공백으로 흘려버린다. 이걸 넣지
        않으면 여러 줄짜리 메시지가 한 줄로 이어붙는다.
        """
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

        레지스트리 쓰기가 막히면 체크만 켜진 채 실제로는 등록되지 않는다. 그러면
        다음 로그인에 안 뜨는 이유를 알 길이 없으므로, 표시를 실제 상태로 되돌리고
        로그에 남긴다.
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

    QSS에 font 속성이 있으면 Qt는 그 값으로 QFont를 새로 만든다. 그런데
    QApplication.setFont()에 걸어 둔 힌팅과 안티앨리어싱 설정은 그 새 폰트로
    따라오지 않는다. QListWidget처럼 항목을 델리게이트가 직접 그리는 위젯에서
    특히 그렇고, 그대로 두면 기본 힌팅으로 그려져 글자가 자글자글해진다.

    스타일이 폰트를 갈아끼우는 시점은 Polish가 아니라 그 뒤에 오는 FontChange다.
    QListWidget에서 이벤트 순서를 찍어 보면 Polish까지는 설정이 살아 있다가
    직후 FontChange에서 기본값으로 덮인다. 그래서 세 시점을 모두 본다.

    고칠 때는 위젯의 현재 폰트를 가져와 두 속성만 바꾼다. QSS가 정한 서체와
    크기는 그대로 두고 렌더링 방식만 되돌리기 위해서다. 이미 규칙대로면 손대지
    않으므로, 우리가 부른 setFont가 다시 FontChange를 부르며 도는 일은 없다.
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
    """서체 파일 하나를 등록하고 패밀리명 목록을 돌려준다.

    파일이 없거나 등록에 실패해도 예외를 내지 않고 빈 목록을 돌려준다.
    """
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

    입력칸을 우클릭하면 나오는 잘라내기·복사·붙여넣기 메뉴는 Qt가 직접 만들고,
    아이콘도 Qt에 딸려 오는 것(:/icons)을 쓴다. **일곱 개가 전부 흰색이라 라이트
    테마에서 묻힌다.** 윤곽선으로 그려진 것(실행 취소·잘라내기·복사·삭제)은
    흐리게나마 보이지만, 면으로 채워진 붙여넣기와 전체 선택은 아예 안 보인다.

    메뉴를 우리가 새로 만들지 않고 열리는 순간에 색만 갈아끼운다. 그 메뉴를 만드는
    곳은 Qt 안쪽이라 우리 손이 닿지 않고, 직접 다시 만들면 항목이 언제 켜지고
    꺼지는지(붙여넣기는 클립보드가 비면 꺼진다)를 전부 따라 해야 한다.

    흰색 단색인 것만 바꾼다. 색이 든 아이콘을 나중에 메뉴에 넣더라도 덮어칠하지
    않기 위해서다. 테마를 바꾸면 색이 따라와야 하므로 열 때마다 지금 색으로 맞춘다.
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

        칠하기 전 원본을 들고 있는다. 한 번 칠하고 나면 더 이상 흰색이 아니라서,
        원본 없이는 테마가 바뀌었을 때 다시 칠할 대상으로 알아보지 못한다.
        (우클릭 때마다 새로 만들어지는 메뉴는 늘 흰 아이콘이라 이 없이도 맞지만,
        한 번 만들어 두고 계속 쓰는 메뉴는 옛 색에 머문다.)
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
    """제 창을 가진 팝업을 모두 같은 모양으로 맞춘다. 메뉴와 콤보박스 펼침 목록.

    **한 곳에서 거는 이유는 콤보박스가 여러 파일에 흩어져 있어서다.** 만드는
    자리마다 손대게 하면 새 콤보박스를 넣을 때 언젠가 빠뜨리고, 그 하나만 모양이
    달라진다. Qt가 직접 만드는 입력칸 우클릭 메뉴처럼 우리가 클래스를 고를 수
    없는 팝업도 여기서 함께 걸린다.

    **손대는 시점은 Polish다.** Show에서 창 힌트를 바꾸면 Qt가 그 자리에서 창을
    숨겨 버려 메뉴가 아예 뜨지 않는다(실측: Show로 걸면 `isVisible()`이 False).
    Polish는 창이 만들어지기 전에 오므로 힌트가 그대로 먹는다. 콤보박스도 같다 -
    Polish 때는 펼침 창이 아직 만들어지지 않아(실측: `WA_WState_Created`가 False)
    투명 속성이 창을 만들 때부터 반영된다. 아이콘 색을 맞추는 `MenuIconTinter`가
    Show를 쓰는 것과 다른 이유가 이것이다.

    이미 힌트가 걸린 `RoundedMenu`에 다시 걸어도 달라지는 것은 없다.
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

    입력창 우클릭 메뉴(잘라내기/붙여넣기/모두 선택)나 표준 대화상자 문구는 Qt가
    제공하는 번역 파일에서 온다. QTranslator를 설치하지 않으면 OS 언어와 무관하게
    영어로 나온다. 실패해도 영어로 동작하므로 예외를 밖으로 내보내지 않는다.
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
    """번들 서체를 등록하고 앱 기본 서체를 지정한다.

    어느 하나가 없거나 실패해도 예외를 밖으로 내보내지 않는다.
    등록된 것까지만 쓰고 나머지는 시스템 서체로 폴백한다.
    """
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
