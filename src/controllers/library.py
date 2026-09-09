"""기록 탭과 즐겨찾기 탭을 맡는다. 저장해 둔 것을 다시 그리고, 검색어로 거르고, 지운다.

**한 모듈에 둔 것은 둘이 실제로 맞물려 있어서다** - 즐겨찾기 신규 확인은 받아 온 회차 중
무엇이 새것인지를 history_store에 물어 가른다. 나누면 그 한 줄 때문에 서로를 부르게 된다.

대기열에 넣는 일은 창의 _request_add_task 하나로 모으고 여기서 직접 하지 않는다 - 중복
확인 창이 그 안에 있어, 우회하면 이미 받은 회차를 묻지도 않고 다시 받는다.
"""

import os
import webbrowser
from typing import Dict, List

from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QCursor

from src.i18n import t
from src.message import confirm, notify
from src.utils import open_file_location
from src.qtparts import RoundedMenu
from src.widgets import (FavoriteItemWidget, HistoryItemWidget,
                         clear_item_widgets)


class LibraryController:
    """기록·즐겨찾기 두 목록을 그리고 거르는 조작 묶음."""

    HISTORY_PAGE_SIZE = 30
    """기록 탭을 열었을 때 처음 그리는 개수.

    **비용이 여기 하나에 몰려 있다.** 목록을 다시 그리는 데 드는 시간은 기록이 몇 개
    쌓였든 이 값에만 비례한다 - 정렬과 거르기는 기록 5,000개에서도 다 합쳐 3ms인데,
    카드를 만드는 것은 100장에 108ms다(캐시된 썸네일을 읽어 푸는 값이 그 3분의 1).
    100에서 30으로 내려 32ms가 됐다.
    """

    HISTORY_MORE_STEP = 15
    """스크롤이 바닥에 닿을 때마다 목록 끝에 덧붙이는 개수.

    첫 쪽(30)보다 작게 둔다 - 덧붙이는 일은 사람이 바닥에서 기다리는 중에 일어나서,
    한 번에 많이 만들수록 그 자리에서 멈칫하는 것이 그대로 드러난다.
    """

    HISTORY_MAX_DISPLAY = 120
    """더 붙이더라도 여기까지만. 남는 것은 목록 끝의 안내 줄이 개수로 알린다.

    30에서 15씩 여섯 번 붙인 값이다. 처음부터 이만큼 그리면 켤 때마다 130ms를 치르는데,
    바닥에 닿을 때만 붙이므로 끝까지 내려 본 사람만 그 값을 나눠 낸다.
    """

    SEARCH_DEBOUNCE_MS = 250
    """검색어가 바뀌고 나서 목록을 다시 그리기까지 기다리는 시간.

    `textChanged`에 바로 걸면 글자마다 목록을 통째로 다시 그린다. 다섯 글자를 치는
    동안 다섯 번이니 그만큼 곱해져 멈칫한다(실측 540ms). 타자가 멎은 뒤 한 번만
    그리면 그 값이 한 번치로 줄어든다. 250ms는 이어 치는 사이보다 길고 멈춘 것을
    알아차리기에는 짧다.
    """

    MAX_FAVORITES = 20
    """즐겨찾기에 담을 수 있는 최대 시리즈 수. 늘어나면 시작할 때 도는 분석도 길어진다."""

    FAV_AUTO_ADD_LIMIT = 2
    """말없이 대기열에 넣어도 되는 신규 회차 수.

    이보다 많으면 선택 창을 띄운다 - 50~70개가 쏟아지면 지금 받고 싶은 영상이 뒤로 밀린다.
    """

    def __init__(self, window):
        self.window = window
        self._history_limit = self.HISTORY_PAGE_SIZE
        self._history_entries = []
        """지금 목록이 보고 있는 전체 항목. 덧붙일 때 저장소를 다시 거르지 않으려고 든다."""
        self._history_search_timer = QTimer(window)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._history_search_timer.timeout.connect(self.reset_history_view)

    def request_history_refresh(self):
        """검색칸이 바뀌었을 때 부른다. 타자가 멎은 뒤에 한 번만 다시 그린다.

        **검색칸에서만 이 길로 온다.** 다운로드가 끝나거나 기록을 지운 뒤처럼 결과를
        바로 봐야 하는 자리는 `refresh_history_list`를 그대로 부른다 - 그쪽은 한 번뿐이라
        미룰 이유가 없고, 미루면 지운 항목이 잠깐 남아 있는 것처럼 보인다.
        """
        self._history_search_timer.start()

    def _current_history_entries(self):
        """검색어와 정렬을 반영한 목록 전체. 여기서는 자르지 않는다."""
        window = self.window
        search_term = window.ui.history_search_input.text().lower()
        entries = window.history_store.sorted_entries()
        if search_term:
            entries = [(url, meta) for url, meta in entries
                       if search_term in meta.get('title', '').lower() or search_term in url.lower()]
        if window.ui.history_sort_combo.currentIndex() == 1:
            entries.sort(key=lambda item: item[1].get('title', ''))
        return entries

    def _add_history_row(self, url: str, meta: dict):
        """카드 한 장을 목록 끝에 붙인다. 표지 그림도 회차 id도 없으면 글자 줄로 세운다."""
        window = self.window
        item = QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole, url)
        if meta.get("series_id") or meta.get("thumbnail_url"):
            widget = HistoryItemWidget(url, meta, window.config.get("theme", "light")); item.setSizeHint(widget.sizeHint())
            window.ui.history_list.addItem(item); window.ui.history_list.setItemWidget(item, widget)
        else:
            title = meta.get("title") or t("card.title_missing"); date = meta.get("date", "")
            item.setText(f"{title}  •  {date}\n{url}"); item.setSizeHint(QSize(0, 90)); window.ui.history_list.addItem(item)

    def _drop_more_notice(self):
        """목록 끝의 안내 줄을 뗀다. 카드는 UserRole에 주소를 들고 있어 구별된다."""
        history_list = self.window.ui.history_list
        last = history_list.count() - 1
        if last >= 0 and history_list.item(last).data(Qt.ItemDataRole.UserRole) is None:
            history_list.takeItem(last)

    def _sync_more_notice(self, total_count: int):
        """남은 개수를 목록 끝에 알린다. 더 붙일 수 있으면 그 말을 대신 적는다."""
        remaining = total_count - self._history_limit
        if remaining <= 0: return
        key = "log.history_more" if self._history_limit >= self.HISTORY_MAX_DISPLAY else "log.history_scroll_more"
        info_item = QListWidgetItem(t(key, count=remaining))
        info_item.setFlags(Qt.ItemFlag.NoItemFlags); info_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.window.ui.history_list.addItem(info_item)

    def refresh_history_list(self):
        """지금 펼쳐 둔 만큼 목록을 다시 그린다.

        **펼친 쪽 수는 그대로 둔다.** 60개까지 내려 본 사람의 다운로드가 끝났다고 목록이
        30개로 줄면, 방금까지 보던 자리가 사라진다.
        """
        window = self.window
        entries = self._current_history_entries()
        self._history_entries = entries
        self._history_limit = min(max(self._history_limit, self.HISTORY_PAGE_SIZE), self.HISTORY_MAX_DISPLAY)

        window.ui.history_empty.set_filtered(bool(window.ui.history_search_input.text()))
        clear_item_widgets(window.ui.history_list)
        for url, meta in entries[:self._history_limit]:
            self._add_history_row(url, meta)
        self._sync_more_notice(len(entries))

    def reset_history_view(self):
        """검색어나 정렬이 바뀌었을 때. 펼친 쪽을 접고 처음부터 다시 센다."""
        self._history_limit = self.HISTORY_PAGE_SIZE
        self.refresh_history_list()

    def load_more_history(self):
        """다음 한 쪽을 목록 끝에 붙인다.

        **다시 그리지 않고 덧붙이는 것이 요점이다.** 통째로 다시 그리면 스크롤이 맨 위로
        튀어, 더 보려고 바닥까지 내린 사람이 그 자리를 잃는다.
        """
        start = self._history_limit
        end = min(start + self.HISTORY_MORE_STEP, self.HISTORY_MAX_DISPLAY, len(self._history_entries))
        if end <= start: return
        self._drop_more_notice()
        for url, meta in self._history_entries[start:end]:
            self._add_history_row(url, meta)
        self._history_limit = end
        self._sync_more_notice(len(self._history_entries))

    def on_history_scrolled(self, value: int):
        """바닥에 닿았을 때만 다음 쪽을 부른다."""
        scroll_bar = self.window.ui.history_list.verticalScrollBar()
        if scroll_bar.maximum() and value >= scroll_bar.maximum():
            self.load_more_history()

    def show_history_menu(self, pos):
        window = self.window
        item = window.ui.history_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        menu.addAction(t("menu.open_in_browser"), lambda: webbrowser.open(url))
        menu.addAction(t("menu.download_again"), lambda: window._request_add_task(url))
        filepath = window.history_store.get_filepath(url)
        if filepath and os.path.exists(filepath):
            menu.addAction(t("menu.open_location"), lambda: open_file_location(filepath))
        menu.addAction(t("menu.remove_from_history"), lambda: self.remove_from_history(url)); menu.exec(QCursor.pos())

    def remove_from_history(self, url: str):
        window = self.window
        window.history_store.remove(url); window.history_store.save(); self.refresh_history_list(); window.append_log(t("log.history_removed", url=url))

    def remove_selected_history(self):
        window = self.window
        selected_items = window.ui.history_list.selectedItems()
        if not selected_items:
            notify(window, t("dialog.notice_title"), t("dialog.select_items_body"),
                   icon_name="tab_history", theme=window.config.get("theme", "light"))
            return
        if confirm(window, t("dialog.delete_confirm_title"),
                   t("dialog.history_delete_body", count=len(selected_items)),
                   icon_name="nav_cache", color_key="danger",
                   theme=window.config.get("theme", "light")):
            for item in selected_items:
                url = item.data(Qt.ItemDataRole.UserRole)
                if url: window.history_store.remove(url)
            window.history_store.save()
            self.refresh_history_list()
            window.append_log(t("log.history_removed_many", count=len(selected_items)))

    def refresh_fav_list(self):
        """검색어에 걸리는 즐겨찾기만 다시 그린다.

        항목을 숨기는 대신 목록을 새로 채운다. GridListWidget은 항목 폭으로 열을 나누므로
        다 채운 뒤 relayout()으로 지금 폭을 다시 먹여야 열이 어긋나지 않는다.
        """
        window = self.window
        search_term = window.ui.fav_search_input.text().strip().lower()
        window.ui.fav_empty.set_filtered(bool(search_term))
        clear_item_widgets(window.ui.fav_list)
        column_width = window.ui.fav_list.column_width()
        for url, meta in window.fav_store.sorted_entries():
            if search_term and (search_term not in (meta.get("title") or "").lower()
                                and search_term not in url.lower()):
                continue
            item = QListWidgetItem(); widget = FavoriteItemWidget(url, meta, window.config.get("theme", "light"))
            item.setSizeHint(QSize(column_width, FavoriteItemWidget.CARD_HEIGHT))
            item.setData(Qt.ItemDataRole.UserRole, url)
            window.ui.fav_list.addItem(item); window.ui.fav_list.setItemWidget(item, widget)
        window.ui.fav_list.relayout()

    def add_favorite(self):
        window = self.window
        if len(window.fav_store.list_series()) >= self.MAX_FAVORITES:
            notify(window, t("dialog.favorites_full_title"),
                   t("dialog.favorites_full_body", maximum=self.MAX_FAVORITES),
                   icon_name="tab_favorites", color_key="warn", theme=window.config.get("theme", "light"))
            return

        url = window.ui.fav_input.text().strip()
        if not url or "/series/" not in url:
            notify(window, t("dialog.notice_title"), t("dialog.favorite_invalid_url"),
                   icon_name="info", color_key="warn", theme=window.config.get("theme", "light"))
            return
        if window.fav_store.exists(url):
            notify(window, t("dialog.notice_title"), t("dialog.favorite_exists"),
                   icon_name="tab_favorites", theme=window.config.get("theme", "light"))
            return

        window.fav_store.add(url)
        window.ui.fav_input.clear()
        window.ui.fav_search_input.clear()
        self.refresh_fav_list()
        window.append_log(t("log.fav_added", url=url))
        window.series_parser.parse('fav-add-check', [url])

    def remove_selected_favorite(self):
        window = self.window
        selected_items = window.ui.fav_list.selectedItems()
        if not selected_items:
            notify(window, t("dialog.notice_title"), t("dialog.select_items_body"),
                   icon_name="tab_favorites", theme=window.config.get("theme", "light"))
            return
        if confirm(window, t("dialog.delete_confirm_title"),
                   t("dialog.favorite_delete_body", count=len(selected_items)),
                   icon_name="nav_cache", color_key="danger",
                   theme=window.config.get("theme", "light")):
            for item in selected_items:
                url = item.data(Qt.ItemDataRole.UserRole); window.fav_store.remove(url); window.append_log(t("log.fav_removed", url=url))
            self.refresh_fav_list()

    def check_all_favorites(self):
        window = self.window
        folder = window.config.get("download_folder")
        if not folder or not os.path.isdir(folder): window.append_log(t("log.fav_no_folder")); return
        urls = window.fav_store.list_series()
        if not urls:
            if window.sender() == window.ui.fav_chk_btn:
                notify(window, t("dialog.notice_title"), t("dialog.no_favorites"),
                       icon_name="tab_favorites", theme=window.config.get("theme", "light"))
            return
        window.append_log(t("log.fav_check_all", count=len(urls))); window.series_parser.parse('fav-check', urls); window.ui.tabs.setCurrentIndex(0)

    def show_fav_menu(self, pos):
        window = self.window
        item = window.ui.fav_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        def check_this_series(): window.series_parser.parse('fav-check', [url]); window.ui.tabs.setCurrentIndex(0)
        menu.addAction(t("menu.check_series"), check_this_series)
        menu.addAction(t("menu.open_in_browser"), lambda: webbrowser.open(url))
        menu.addAction(t("menu.remove_favorite"), lambda: self.remove_favorite(url)); menu.exec(QCursor.pos())

    def remove_favorite(self, url: str):
        window = self.window
        window.fav_store.remove(url); self.refresh_fav_list(); window.append_log(t("log.fav_removed", url=url))

    def on_fav_check_parsed(self, series_url: str, series_title: str, episode_info: List[Dict[str, str]]):
        """확인이 끝난 즐겨찾기 시리즈에서 신규 회차를 가려낸다.

        FAV_AUTO_ADD_LIMIT 이하면 그냥 받고, 그보다 많으면 선택 창을 띄운다.

        **결과를 쓰기 전에 그 즐겨찾기가 아직 있는지 본다.** 분석은 72화 기준 60초까지
        걸려 그동안 사용자가 지울 수 있는데, 그대로 이어가면 지운 시리즈가 되살아나고
        그 신규 회차까지 대기열에 들어간다.
        """
        window = self.window
        if not window.fav_store.touch_last_check(series_url, series_title):
            return
        self.refresh_fav_list()
        label = series_title or series_url
        new_episodes = [ep for ep in episode_info if not window.history_store.exists(ep['url'])]
        if not new_episodes:
            return
        if len(new_episodes) <= self.FAV_AUTO_ADD_LIMIT:
            added_count = 0
            for episode in new_episodes:
                if window._request_add_task(episode['url'], title=episode.get('title', ''),
                                            thumbnail=episode.get('thumbnail_url', '')):
                    added_count += 1
            if added_count:
                window.append_log(t("log.fav_new_added", label=label, count=added_count))
            return
        window.append_log(t("log.fav_new_found", label=label, count=len(new_episodes)))
        window._add_from_selection(new_episodes, t("log.fav_new_label", label=label))

    def on_fav_add_check_parsed(self, series_url: str, series_title: str):
        """즐겨찾기에 갓 담은 시리즈의 제목을 받아 적는다.

        제목만 물어보는 분석이라 회차 목록은 오지 않는다. 못 가져와도 등록은 이미 끝났다.
        **답이 오기 전에 지웠으면 조용히 넘어간다** - 적어 넣으면 지운 것이 되살아난다.
        """
        window = self.window
        if series_title:
            if not window.fav_store.touch_last_check(series_url, series_title):
                return
            self.refresh_fav_list()
            window.append_log(t("log.fav_title_updated", title=series_title))
        else:
            window.append_log(t("log.fav_title_failed", url=series_url))
