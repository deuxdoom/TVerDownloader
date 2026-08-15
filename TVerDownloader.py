import sys, os, webbrowser
from html import escape
from typing import List, Dict, Optional
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QListWidgetItem, QMessageBox, QSystemTrayIcon, QFileDialog, QWidget,
                             QAbstractSpinBox, QLineEdit, QTextEdit)
from PyQt6.QtCore import Qt, QEvent, QObject, QTimer, QSize, QLocale, QTranslator, QLibraryInfo
from PyQt6.QtGui import QCursor, QGuiApplication, QFontDatabase, QFont, QKeySequence, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src import autostart, shortcuts
from src.utils import (load_config, save_config, handle_exception, open_file_location,
                       ERROR_STATUSES, localized_app_name, get_resource_path,
                       is_media_url, match_tver_url)
from src.qss import build_qss, palette, UI_FONT_FALLBACKS
from src.message import confirm, notify
from src.about_dialog import AboutDialog
from src.bulk_dialog import BulkAddDialog
from src.dialogs import SettingsDialog
from src.series_dialog import SeriesSelectionDialog
from src.history_store import HistoryStore
from src.favorites_store import FavoritesStore
from src.widgets import DownloadItemWidget, FavoriteItemWidget, HistoryItemWidget, RoundedMenu
from src.updater import maybe_show_update
from src.threads.setup_thread import SetupThread
from src.ui.main_window_ui import MainWindowUI
from src.series_parser import SeriesParser
from src.download_manager import DownloadManager

APP_VERSION = "3.2.0"
SOCKET_NAME = "TVerDownloader_IPC_Socket"
FAV_AUTO_ADD_LIMIT = 2

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{localized_app_name()} v{APP_VERSION}")
        self.force_quit = False; self.env_ready = False; self.config = load_config()
        self._clipboard_connected = False; self._last_clipboard_url = ""; self._bulk_dialog = None
        self._shortcuts: List[QShortcut] = []; self._guarded_shortcuts: List[QShortcut] = []
        self.setAcceptDrops(True)
        self.history_store = HistoryStore(); self.history_store.load(); self.fav_store = FavoritesStore("favorites.json"); self.fav_store.load()
        self.ui = MainWindowUI(self); self.ui.setup_ui(); self.tray_icon = QSystemTrayIcon(self); self.ui.setup_tray(APP_VERSION)
        self.series_parser = SeriesParser(ytdlp_path="", config=self.config)
        self.download_manager = DownloadManager(self.config, self.history_store)
        self._connect_signals(); self._set_input_enabled(False)
        self.apply_theme(self.config.get("theme", "light"), persist=False)
        self.set_always_on_top(self.config.get("always_on_top", False), init=True)
        self.ui.set_log_visible(self.config.get("log_visible", True))
        self.apply_clipboard_watch(self.config.get("clipboard_watch", False))
        self.refresh_history_list(); self.refresh_fav_list()
        self.apply_shortcuts()
        QApplication.instance().focusChanged.connect(self._sync_shortcut_guard)
        self.append_log("프로그램 시작. 환경 설정을 시작합니다...")
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
            self.apply_clipboard_watch(self.config.get("clipboard_watch", False))
            self.apply_shortcuts()
            self.append_log(f"설정이 저장되었습니다. 동시 다운로드: {self.config['max_concurrent_downloads']}개")
            self.refresh_history_list()
            self.refresh_fav_list()

    def apply_theme(self, theme: str, persist: bool = True):
        """QSS와 아이콘 색을 한 번에 새 테마로 맞춘다."""
        self.config["theme"] = theme
        if persist:
            save_config(self.config)
        QApplication.instance().setStyleSheet(build_qss(theme))
        self.ui.apply_theme(theme)
        for list_widget in (self.ui.download_list, self.ui.history_list, self.ui.fav_list):
            for i in range(list_widget.count()):
                widget = list_widget.itemWidget(list_widget.item(i))
                if hasattr(widget, "apply_theme"):
                    widget.apply_theme(theme)

    def apply_clipboard_watch(self, enabled: bool):
        """클립보드 감시를 켜거나 끈다.

        끄면 시그널 연결 자체를 끊는다. 콜백 안에서 그냥 돌아 나오게 두면 꺼 놓고도
        복사할 때마다 클립보드를 읽게 되는데, 이 기능을 꺼림칙해하는 쪽에서는
        그것부터가 문제다.
        """
        clipboard = QGuiApplication.clipboard()
        if enabled and not self._clipboard_connected:
            clipboard.dataChanged.connect(self._on_clipboard_changed)
            self._clipboard_connected = True
        elif not enabled and self._clipboard_connected:
            try:
                clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            except TypeError:
                pass
            self._clipboard_connected = False

    def _on_clipboard_changed(self):
        """복사된 TVer 주소를 받아 둘 자리를 정한다.

        받기까지 자동으로 하지는 않는다. 주소가 맞는지 눈으로 보고 누르는 편이
        낫고, 잘못 복사한 것이 곧바로 대기열에 들어가면 되돌리기 번거롭다.

        입력창은 한 칸이라 둘째 주소부터는 갈 곳이 없었다. 예전에는 그때 그냥
        돌아 나와서, 주소를 연달아 복사하면 감시가 꺼진 것처럼 보였다. 이제는
        이미 든 주소와 함께 다중 추가 창으로 옮기고, 그 창이 열려 있는 동안은
        복사할 때마다 한 줄씩 쌓는다.

        입력창에 TVer 주소가 아닌 글이 들어 있으면 예전처럼 아무것도 하지 않는다.
        직접 적던 내용을 치우고 그 자리를 가져갈 이유가 없다.

        시리즈 주소도 즐겨찾기 칸이 아니라 이 흐름으로 보낸다. 복사한 사람이
        지금 받고 싶은 것인지 즐겨찾기에 두고 싶은 것인지 알 수 없으므로, 손이
        가 있는 자리 하나로 모은다.
        """
        url = match_tver_url(QGuiApplication.clipboard().text())
        if not url or url == self._last_clipboard_url:
            return
        if self._bulk_dialog is not None:
            self._last_clipboard_url = url
            if self._bulk_dialog.append_url(url):
                self.append_log(f"[클립보드] 다중 추가 창에 넣었습니다: {url}")
            return
        pending = match_tver_url(self.ui.url_input.text())
        if pending and pending != url:
            self._last_clipboard_url = url
            self.append_log("[클립보드] 주소가 하나 더 들어와 다중 추가 창으로 모읍니다.")
            self.ui.url_input.clear()
            if not self.open_bulk_add([pending, url]):
                self.ui.url_input.setText(pending)
            return
        if self.ui.url_input.text().strip():
            return
        self._last_clipboard_url = url
        self.ui.url_input.setText(url)
        self.append_log(f"[클립보드] 주소를 입력창에 넣었습니다: {url}")

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
            "delete_selected": self._delete_selected_download_items,
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
        if self._urls_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """dragEnter에서 받아 놓고도 이걸 빼면 커서가 금지 표시로 바뀐다."""
        if self._urls_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = self._urls_from_mime(event.mimeData())
        if not urls:
            event.ignore(); return
        event.setDropAction(Qt.DropAction.CopyAction); event.accept()
        self._accept_dropped_urls(urls)

    def _urls_from_mime(self, mime) -> List[str]:
        """드롭된 데이터에서 TVer 주소만 순서대로 골라낸다.

        브라우저는 주소 하나를 끌어도 text/uri-list와 text/plain을 함께 실어 보낸다.
        양쪽을 다 보고 중복을 걷어내야 같은 주소가 두 번 들어오지 않는다. 판별은
        클립보드와 같은 전체 일치 규칙이라, 주소가 아닌 것을 끌어다 놓으면 창이
        아예 받지 않는다.
        """
        candidates: List[str] = []
        if mime.hasUrls():
            candidates.extend(url.toString() for url in mime.urls())
        if mime.hasText():
            candidates.extend(mime.text().splitlines())
        found: List[str] = []
        for candidate in candidates:
            url = match_tver_url(candidate)
            if url and url not in found:
                found.append(url)
        return found

    def _accept_dropped_urls(self, urls: List[str]):
        """끌어다 놓은 주소를 개수에 따라 다른 흐름으로 넘긴다.

        하나면 입력창에 채우기만 한다. 클립보드와 달리 이미 들어 있는 내용을
        덮어쓰는데, 창을 겨냥해 끌어다 놓은 것은 지금 이걸 받겠다는 뜻이라
        직전에 적어 둔 것보다 나중 의사가 앞선다.

        여럿이면 다중 추가 창을 미리 채워서 연다. 곧바로 대기열에 넣지 않는 것은
        무엇이 들어왔는지 확인하고 지울 기회를 주기 위해서다.
        """
        if len(urls) == 1:
            self.ui.url_input.setText(urls[0]); self.ui.url_input.setFocus()
            self.append_log(f"[드롭] 주소를 입력창에 넣었습니다: {urls[0]}")
            return
        self.append_log(f"[드롭] 주소 {len(urls)}개를 받았습니다. 다중 추가 창을 엽니다.")
        self.open_bulk_add(urls)

    def _delete_selected_download_items(self):
        selected_items = self.ui.download_list.selectedItems()
        if not selected_items: return
        rows_to_delete = sorted([self.ui.download_list.row(item) for item in selected_items], reverse=True)
        for row in rows_to_delete:
            item = self.ui.download_list.item(row); widget = self.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget): continue
            url = widget.url
            if url in self.download_manager._active_threads: continue
            if url in self.download_manager._task_queue: self.download_manager.remove_task_from_queue(url)
            self._remove_download_row(row)

    def _sync_selection_styles(self, list_widget):
        """목록 위젯 안의 항목들에게 자신의 선택 여부를 알린다."""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if hasattr(widget, "set_selected"):
                widget.set_selected(item.isSelected())

    def _remove_download_row(self, row: int):
        """카드를 목록에서 뺀다. 애니메이션과 콜백을 먼저 끊어야 리소스가 남지 않는다."""
        item = self.ui.download_list.item(row)
        if item is None:
            return
        widget = self.ui.download_list.itemWidget(item)
        if isinstance(widget, DownloadItemWidget):
            widget.cleanup()
        self.ui.download_list.takeItem(row)

    def _connect_signals(self):
        self.ui.add_button.clicked.connect(self.process_input_url); self.ui.url_input.returnPressed.connect(self.process_input_url)
        self.ui.bulk_button.clicked.connect(lambda: self.open_bulk_add()); self.ui.settings_button.clicked.connect(self.open_settings)
        self.ui.about_button.clicked.connect(
            lambda: AboutDialog(APP_VERSION, self, self.config.get("theme", "light")).exec())
        self.ui.clear_log_button.clicked.connect(self.clear_log); self.ui.on_top_btn.toggled.connect(self.set_always_on_top)
        self.ui.theme_button.clicked.connect(self.toggle_theme)
        self.ui.log_toggle_btn.clicked.connect(self.toggle_log_panel)
        self.ui.clear_completed_button.clicked.connect(self._clear_completed_downloads)
        self.ui.cancel_selected_button.clicked.connect(self._cancel_selected_downloads)
        self.ui.download_list.itemSelectionChanged.connect(self._sync_cancel_button)
        self.ui.download_list.customContextMenuRequested.connect(self.show_download_context_menu)
        for list_widget in (self.ui.download_list, self.ui.history_list, self.ui.fav_list):
            list_widget.itemSelectionChanged.connect(
                lambda lw=list_widget: self._sync_selection_styles(lw))
        self.ui.history_list.customContextMenuRequested.connect(self.show_history_menu)
        self.ui.history_search_input.textChanged.connect(self.refresh_history_list)
        self.ui.fav_search_input.textChanged.connect(self.refresh_fav_list)
        self.ui.history_sort_combo.currentIndexChanged.connect(self.refresh_history_list)
        self.ui.fav_add_btn.clicked.connect(self.add_favorite); self.ui.fav_del_btn.clicked.connect(self.remove_selected_favorite)
        self.ui.fav_chk_btn.clicked.connect(self.check_all_favorites); self.ui.fav_list.customContextMenuRequested.connect(self.show_fav_menu)
        self.download_manager.log.connect(self.append_log); self.download_manager.item_added.connect(self._add_item_widget)
        self.download_manager.heading.connect(self.append_heading)
        self.download_manager.progress_updated.connect(self._update_item_widget); self.download_manager.task_finished.connect(self._on_task_finished)
        self.download_manager.queue_changed.connect(lambda q, a: self.ui.queue_count_label.setText(f"{q} 대기 / {a} 진행"))
        self.download_manager.all_tasks_completed.connect(self._on_all_downloads_finished)
        self.series_parser.log.connect(lambda ctx, msg: self.append_log(msg)); self.series_parser.finished.connect(self._on_series_parsed)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def refresh_history_list(self):
        search_term = self.ui.history_search_input.text().lower(); sort_index = self.ui.history_sort_combo.currentIndex()
        all_entries = self.history_store.sorted_entries()
        if search_term: entries_to_show = [(url, meta) for url, meta in all_entries if search_term in meta.get('title', '').lower() or search_term in url.lower()]
        else: entries_to_show = all_entries
        if sort_index == 1: entries_to_show.sort(key=lambda item: item[1].get('title', ''))

        MAX_DISPLAY = 100
        total_count = len(entries_to_show)
        display_entries = entries_to_show[:MAX_DISPLAY]

        self.ui.history_list.clear()
        for url, meta in display_entries:
            item = QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole, url)
            if meta.get("series_id") or meta.get("thumbnail_url"):
                widget = HistoryItemWidget(url, meta, self.config.get("theme", "light")); item.setSizeHint(widget.sizeHint())
                self.ui.history_list.addItem(item); self.ui.history_list.setItemWidget(item, widget)
            else:
                title = meta.get("title", "(제목 없음)"); date = meta.get("date", "")
                item.setText(f"{title}  •  {date}\n{url}"); item.setSizeHint(QSize(0, 90)); self.ui.history_list.addItem(item)

        if total_count > MAX_DISPLAY:
            info_item = QListWidgetItem(f"... 외 {total_count - MAX_DISPLAY}개의 이전 기록이 있습니다. (검색하여 찾을 수 있습니다)")
            info_item.setFlags(Qt.ItemFlag.NoItemFlags); info_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ui.history_list.addItem(info_item)

    def _process_url(self, url: str):
        if not self.env_ready: self.append_log("[알림] 아직 프로그램 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해주세요."); return
        if not self._ensure_download_folder(): self.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다."); return
        if "/series/" in url:
            self.append_log(f"[시리즈] 분석을 시작합니다: {url}")
            self.series_parser.parse('single', [url])
        else:
            self._request_add_task(url)

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

    def _cancel_selected_downloads(self):
        """선택한 항목을 상태에 맞게 정리한다.

        진행 중이면 중지하고 카드는 남긴다(취소됨으로 보이고 재다운로드할 수 있다).
        대기 중이면 대기열에서 빼고 목록에서도 지운다. 이미 끝난 항목은 건드리지
        않는다. 그쪽은 '완료 항목 삭제'가 맡는다.
        """
        selected_items = self.ui.download_list.selectedItems()
        if not selected_items:
            return
        rows = sorted((self.ui.download_list.row(item) for item in selected_items), reverse=True)
        stopped = removed = 0
        for row in rows:
            item = self.ui.download_list.item(row)
            widget = self.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget):
                continue
            url = widget.url
            if (url in self.download_manager._active_threads
                    or url in self.download_manager._active_conversions):
                self.download_manager.stop_task(url)
                stopped += 1
            elif url in self.download_manager._task_queue:
                if self.download_manager.remove_task_from_queue(url):
                    self._remove_download_row(row)
                    removed += 1
        parts = []
        if stopped: parts.append(f"진행 중 {stopped}개 중지")
        if removed: parts.append(f"대기 중 {removed}개 제거")
        self.append_log("[대기열] " + (", ".join(parts) if parts
                                      else "선택한 항목 중 중지하거나 뺄 것이 없습니다."))

    def _sync_cancel_button(self):
        self.ui.cancel_selected_button.setEnabled(bool(self.ui.download_list.selectedItems()))

    def _clear_completed_downloads(self):
        for i in range(self.ui.download_list.count() - 1, -1, -1):
            item = self.ui.download_list.item(i); widget = self.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget): continue
            url = widget.url; is_active = url in self.download_manager._active_threads; is_queued = url in self.download_manager._task_queue
            if not is_active and not is_queued: self._remove_download_row(i)

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

    BAD_URL_PREVIEW = 5
    """알림 창에 그대로 보여 줄 잘못된 줄 수. 나머지는 개수로만 줄인다.

    스무 줄을 통째로 붙여 놓으면 창이 화면을 넘고, 어차피 한 줄만 봐도 무엇을
    잘못 넣었는지 알 수 있다.
    """

    BAD_URL_ELIDE = 42
    """알림 창에 보여 줄 한 줄의 최대 길이. 넘으면 뒤를 줄인다."""

    def _notify_bad_url(self, title: str, lead: str, rejected: List[str]):
        """주소가 아닌 줄을 알린다.

        어느 줄이 걸렸는지 보여 준다. '주소가 아닙니다'만으로는 여러 줄을 넣었을 때
        어디를 고쳐야 할지 알 수 없다.
        """
        shown = [self._elide(text, self.BAD_URL_ELIDE)
                 for text in rejected[:self.BAD_URL_PREVIEW]]
        left = len(rejected) - len(shown)
        if left:
            shown.append(f"... 외 {left}개")
        body = "\n".join([lead, "", *shown, "",
                          "http:// 또는 https:// 로 시작하는",
                          "영상 페이지 주소를 넣어주세요."])
        notify(self, title, body, icon_name="info", color_key="warn",
               theme=self.config.get("theme", "light"))

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        """긴 글을 앞부분만 남기고 줄인다."""
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def process_input_url(self):
        """입력창의 주소를 받는다. 주소가 아니면 알리고 그대로 둔다.

        예전에는 무엇이 들었든 yt-dlp에 넘겼다. 문장이나 낱말을 잘못 붙여넣으면
        카드가 하나 생겼다가 오류로 끝나고, 왜 실패했는지는 로그를 봐야 알 수 있었다.

        입력칸을 비우지 않는 이유는, 여기까지 온 글은 대개 고쳐서 다시 쓸 것이기
        때문이다. 지워 버리면 붙여넣은 것을 다시 찾아와야 한다.
        """
        url = self.ui.url_input.text().strip()
        if not url: return
        if not is_media_url(url):
            self._notify_bad_url("주소를 확인해주세요",
                                 "다운로드할 수 있는 주소가 아닙니다.", [url])
            return
        self._process_url(url); self.ui.url_input.clear()

    def _request_add_task(self, url: str) -> bool:
        if self.history_store.exists(url):
            again = confirm(self, "중복 다운로드",
                            f"이미 다운로드한 항목입니다:\n\n{self.history_store.get_title(url)}\n\n다시 다운로드할까요?",
                            icon_name="download", theme=self.config.get("theme", "light"))
            if not again: self.append_log(f"[알림] 중복 다운로드 취소: {url}"); return False
        return self.download_manager.add_task(url)

    def open_bulk_add(self, initial_urls: Optional[List[str]] = None) -> bool:
        """다중 추가 창을 연다. initial_urls를 주면 그 목록으로 채워서 연다.

        창을 실제로 띄웠는지 돌려준다. 클립보드에서 모아 넘길 때는 입력창을 비운
        뒤에 부르므로, 준비가 안 돼 돌아 나온 경우 호출부가 원래 주소를 되돌려
        놓아야 한다.

        떠 있는 동안 self._bulk_dialog에 자기를 걸어 둔다. exec()가 중첩 이벤트
        루프라서 그 사이에도 클립보드 감시가 계속 돌고, 새 주소를 이 창에 넣으려면
        어느 창이 열려 있는지 알아야 한다.
        """
        if not self.env_ready:
            self.append_log("[알림] 아직 프로그램 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해주세요.")
            return False
        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 선택되지 않아 작업이 취소되었습니다.")
            return False
        dialog = BulkAddDialog(self, initial_urls)
        self._bulk_dialog = dialog
        try:
            accepted = dialog.exec()
        finally:
            self._bulk_dialog = None
        if accepted:
            urls = dialog.get_urls()
            rejected = [u for u in urls if not is_media_url(u)]
            urls = [u for u in urls if is_media_url(u)]
            if rejected:
                self.append_log(f"[알림] 주소가 아닌 {len(rejected)}줄을 건너뜁니다.")
                self._notify_bad_url("건너뛴 줄이 있습니다",
                                     "주소가 아니어서 넣지 않은 줄입니다.", rejected)
            normal_urls = [u for u in urls if "/series/" not in u]
            series_urls = [u for u in urls if "/series/" in u]
            for url in normal_urls: self._request_add_task(url)
            if series_urls: self.series_parser.parse('bulk', series_urls)
        return True

    def _on_setup_finished(self, ok: bool, ytdlp_path: str, ffmpeg_path: str):
        if not ok: self.append_log("[오류] 초기 준비 실패: yt-dlp/ffmpeg를 준비하지 못했습니다."); QMessageBox.critical(self, "오류", "초기 준비에 실패했습니다. 로그를 확인하세요."); return
        self.download_manager.set_paths(ytdlp_path, ffmpeg_path); self.series_parser.set_ytdlp_path(ytdlp_path); self.env_ready = True
        self._set_input_enabled(True)
        self.append_notice("안내", ["TVer는 일본 지역 제한이 있습니다.",
                                    "원활한 다운로드를 위해 일본 VPN을 켜고 사용해주세요."])
        self.append_log("환경 설정 완료. 다운로드를 시작할 수 있습니다.")
        QTimer.singleShot(1000, lambda: maybe_show_update(self, APP_VERSION, self.append_log))
        if self.config.get("auto_check_favorites_on_start", True):
            QTimer.singleShot(2500, self.check_all_favorites)

    def _add_from_selection(self, episode_info: List[Dict[str, str]], label: str):
        """에피소드 선택 창을 띄우고, 고른 것만 대기열에 넣는다."""
        dialog = SeriesSelectionDialog(episode_info, self)
        if not dialog.exec():
            self.append_log(f"{label} 에피소드 추가를 취소했습니다.")
            return
        selected_urls = dialog.get_selected_urls()
        if not selected_urls:
            self.append_log(f"{label} 선택된 에피소드가 없어 추가하지 않았습니다.")
            return
        added_count = 0
        for url in selected_urls:
            if self._request_add_task(url): added_count += 1
        self.append_log(f"{label} 선택한 {added_count}개 에피소드를 추가했습니다.")

    def _on_series_parsed(self, context: str, series_url: str, series_title: str, episode_info: List[Dict[str, str]]):
        """분석이 끝난 시리즈를 요청 맥락에 맞게 처리한다.

        즐겨찾기 확인은 신규가 FAV_AUTO_ADD_LIMIT 이하면 그냥 받고, 그보다 많으면
        선택 창을 띄운다. 회차가 수십 개인 시리즈를 확인 없이 대기열에 통째로
        쏟아부으면 정작 지금 받고 싶은 영상이 그 뒤에 밀린다.
        """
        if context in ('single', 'bulk'):
            if not episode_info: self.append_log(f"[{context}] '{series_url}' 시리즈에서 에피소드를 찾지 못했습니다."); return
            self._add_from_selection(episode_info, f"[{context}] 시리즈에서")

        elif context == 'fav-check':
            self.fav_store.touch_last_check(series_url, series_title)
            self.refresh_fav_list()
            label = series_title or series_url
            new_episodes = [ep for ep in episode_info if not self.history_store.exists(ep['url'])]
            if not new_episodes:
                return
            if len(new_episodes) <= FAV_AUTO_ADD_LIMIT:
                added_count = 0
                for episode in new_episodes:
                    if self._request_add_task(episode['url']): added_count += 1
                if added_count:
                    self.append_log(f"[즐겨찾기] '{label}'에서 신규 에피소드 {added_count}개를 추가했습니다.")
                return
            self.append_log(f"[즐겨찾기] '{label}'에서 신규 에피소드 {len(new_episodes)}개를 찾았습니다. 받을 항목을 선택하세요.")
            self._add_from_selection(new_episodes, f"[즐겨찾기] '{label}'에서")

        elif context == 'fav-add-check':
            if series_title:
                self.fav_store.touch_last_check(series_url, series_title)
                self.refresh_fav_list()
                self.append_log(f"[즐겨찾기] 시리즈 제목 업데이트: {series_title}")
            else:
                self.append_log(f"[알림] 즐겨찾기 추가 시 '{series_url}'의 제목을 가져오지 못했습니다.")

    def _add_item_widget(self, url: str):
        existing = self._find_item_widget(url)
        if isinstance(existing, DownloadItemWidget):
            existing.reset_for_retry()
            return
        item = QListWidgetItem(); widget = DownloadItemWidget(url, self.config.get("theme", "light"))
        widget.play_requested.connect(self.play_file)
        widget.open_folder_requested.connect(open_file_location)
        item.setSizeHint(widget.sizeHint())
        self.ui.download_list.insertItem(0, item); self.ui.download_list.setItemWidget(item, widget)

    def _find_item_widget(self, url: str) -> Optional[QWidget]:
        for i in range(self.ui.download_list.count()):
            item = self.ui.download_list.item(i); widget = self.ui.download_list.itemWidget(item)
            if hasattr(widget, 'url') and widget.url == url: return widget
        return None

    def _update_item_widget(self, url: str, payload: Dict):
        widget = self._find_item_widget(url)
        if isinstance(widget, DownloadItemWidget): widget.update_progress(payload)

    def _on_task_finished(self, url: str, success: bool, final_filepath: str, meta: dict):
        widget = self._find_item_widget(url)
        if not widget or not isinstance(widget, DownloadItemWidget): return
        if success and final_filepath:
            title = meta.get('title', widget.title_label.text())
            series_id = meta.get('series_id'); thumbnail_url = meta.get('thumbnail')
            self.history_store.add(url, title, final_filepath, series_id=series_id, thumbnail_url=thumbnail_url)
            self.history_store.save(); self.refresh_history_list()

    def _on_all_downloads_finished(self):
        self.append_log("모든 다운로드가 완료되었습니다.")
        self.tray_icon.showMessage("다운로드 완료", "모든 작업이 끝났습니다!", self.windowIcon(), 5000)

    def show_download_context_menu(self, pos):
        item = self.ui.download_list.itemAt(pos)
        if not item: return
        widget = self.ui.download_list.itemWidget(item)
        if not isinstance(widget, DownloadItemWidget): return
        selected = self.ui.download_list.selectedItems()
        if len(selected) > 1 and item in selected:
            menu = RoundedMenu()
            menu.addAction(f"선택한 {len(selected)}개 중지 · 대기열에서 제거",
                           self._cancel_selected_downloads)
            menu.addAction(f"선택한 {len(selected)}개 목록에서 삭제",
                           self._delete_selected_download_items)
            menu.exec(QCursor.pos())
            return
        url = widget.url; menu = RoundedMenu()
        if url in self.download_manager._active_threads or url in self.download_manager._active_conversions:
            menu.addAction("중지", lambda: self.download_manager.stop_task(url))
        elif url in self.download_manager._task_queue:
            def remove_from_queue():
                if self.download_manager.remove_task_from_queue(url): self._remove_download_row(self.ui.download_list.row(item))
            menu.addAction("대기열에서 제거", remove_from_queue)
        else:
            if widget.status in ERROR_STATUSES:
                menu.addAction("재다운로드", lambda: self._retry_download(url))
            menu.addAction("목록에서 삭제", lambda: self._remove_download_row(self.ui.download_list.row(item)))
        if widget.final_filepath and os.path.exists(widget.final_filepath):
            menu.addAction("파일 위치 열기", lambda: open_file_location(widget.final_filepath))
        menu.exec(QCursor.pos())

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

    def show_history_menu(self, pos):
        item = self.ui.history_list.itemAt(pos);
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        menu.addAction("URL 복사", lambda: QGuiApplication.clipboard().setText(url)); menu.addAction("다시 다운로드", lambda: self._request_add_task(url))
        menu.addAction("기록에서 제거", lambda: self.remove_from_history(url)); menu.exec(QCursor.pos())

    def remove_from_history(self, url: str):
        self.history_store.remove(url); self.history_store.save(); self.refresh_history_list(); self.append_log(f"[알림] 기록에서 제거됨: {url}")

    def refresh_fav_list(self):
        """검색어에 걸리는 즐겨찾기만 다시 그린다.

        기록 탭과 같은 방식이다. 항목을 숨기는 대신 목록을 새로 채운다.
        GridListWidget은 항목 폭으로 열을 나누므로, 다 채운 뒤 relayout()으로
        지금 폭에 맞는 크기를 다시 먹여야 열이 어긋나지 않는다.
        """
        search_term = self.ui.fav_search_input.text().strip().lower()
        self.ui.fav_list.clear()
        column_width = self.ui.fav_list.column_width()
        for url, meta in self.fav_store.sorted_entries():
            if search_term and (search_term not in (meta.get("title") or "").lower()
                                and search_term not in url.lower()):
                continue
            item = QListWidgetItem(); widget = FavoriteItemWidget(url, meta, self.config.get("theme", "light"))
            item.setSizeHint(QSize(column_width, FavoriteItemWidget.CARD_HEIGHT))
            item.setData(Qt.ItemDataRole.UserRole, url)
            self.ui.fav_list.addItem(item); self.ui.fav_list.setItemWidget(item, widget)
        self.ui.fav_list.relayout()

    def add_favorite(self):
        MAX_FAVORITES = 20
        if len(self.fav_store.list_series()) >= MAX_FAVORITES:
            QMessageBox.information(self, "즐겨찾기 개수 초과",
                                      f"즐겨찾기는 최대 {MAX_FAVORITES}개까지 추가할 수 있습니다.\n\n"
                                      "새로운 시리즈를 추가하려면, 시청이 종료되었거나\n"
                                      "자주 확인하지 않는 시리즈를 목록에서 먼저 삭제해주세요.")
            return

        url = self.ui.fav_input.text().strip()
        if not url or "/series/" not in url:
            QMessageBox.information(self, "알림", "유효한 TVer 시리즈 URL을 입력하세요.")
            return
        if self.fav_store.exists(url):
            QMessageBox.information(self, "알림", "이미 즐겨찾기에 등록된 시리즈입니다.")
            return

        self.fav_store.add(url)
        self.ui.fav_input.clear()
        self.ui.fav_search_input.clear()
        self.refresh_fav_list()
        self.append_log(f"[즐겨찾기] 추가됨: {url}. 시리즈 제목 확인 중...")
        self.series_parser.parse('fav-add-check', [url])

    def remove_selected_favorite(self):
        selected_items = self.ui.fav_list.selectedItems()
        if not selected_items: QMessageBox.information(self, "알림", "삭제할 항목을 목록에서 선택하세요."); return
        if confirm(self, "삭제 확인", f"{len(selected_items)}개의 항목을 삭제할까요?",
                   icon_name="nav_cache", color_key="danger",
                   theme=self.config.get("theme", "light")):
            for item in selected_items:
                url = item.data(Qt.ItemDataRole.UserRole); self.fav_store.remove(url); self.append_log(f"[즐겨찾기] 삭제: {url}")
            self.refresh_fav_list()

    def check_all_favorites(self):
        folder = self.config.get("download_folder")
        if not folder or not os.path.isdir(folder): self.append_log("[알림] 다운로드 폴더가 설정되지 않아 시작 시 즐겨찾기 자동 확인을 건너뜁니다."); return
        urls = self.fav_store.list_series()
        if not urls:
            if self.sender() == self.ui.fav_chk_btn: QMessageBox.information(self, "알림", "등록된 즐겨찾기가 없습니다.")
            return
        self.append_log(f"[즐겨찾기] 전체 확인 시작 ({len(urls)}개 시리즈)"); self.series_parser.parse('fav-check', urls); self.ui.tabs.setCurrentIndex(0)

    def show_fav_menu(self, pos):
        item = self.ui.fav_list.itemAt(pos);
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        def check_this_series(): self.series_parser.parse('fav-check', [url]); self.ui.tabs.setCurrentIndex(0)
        menu.addAction("이 시리즈 확인", check_this_series); menu.addAction("브라우저에서 열기", lambda: webbrowser.open(url))
        menu.addAction("삭제", lambda: self.remove_favorite(url)); menu.exec(QCursor.pos())

    def remove_favorite(self, url: str):
        self.fav_store.remove(url); self.refresh_fav_list(); self.append_log(f"[즐겨찾기] 삭제: {url}")

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.bring_to_front()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide(); self.tray_icon.showMessage(localized_app_name(), "프로그램이 트레이로 이동했습니다.", self.windowIcon(), 2000)

    def closeEvent(self, event):
        if self.force_quit: event.accept(); return
        if self.config.get("close_action", "exit") == "tray":
            event.ignore(); self.hide()
            self.tray_icon.showMessage(localized_app_name(), "프로그램이 트레이로 이동했습니다.", self.windowIcon(), 2000)
            return
        if confirm(self, "종료 확인", "종료하시겠습니까?",
                   icon_name="cancel", color_key="danger",
                   theme=self.config.get("theme", "light")):
            self.quit_application(); event.accept()
        else:
            event.ignore()

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

    def quit_application(self):
        self.append_log("프로그램을 종료합니다...")
        for url in list(self.download_manager._active_threads.keys()): self.download_manager.stop_task(url)
        self.force_quit = True; self.tray_icon.hide(); QApplication.instance().quit()

    def _retry_download(self, url: str):
        if url in self.download_manager._active_threads or url in self.download_manager._active_conversions or url in self.download_manager._task_queue:
            return
        if not self._ensure_download_folder():
            self.append_log("[알림] 다운로드 폴더가 설정되지 않아 재다운로드를 취소했습니다.")
            return
        self.download_manager.reset_for_redownload(url)
        widget = self._find_item_widget(url)
        if isinstance(widget, DownloadItemWidget):
            widget.reset_for_retry()
        self.download_manager.add_task(url)

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
