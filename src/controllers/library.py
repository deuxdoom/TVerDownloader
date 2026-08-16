"""기록 탭과 즐겨찾기 탭을 맡는다.

두 탭은 하는 일의 성격이 같다. **저장해 둔 것을 다시 그리고, 검색어로 거르고,
우클릭으로 지운다.** 목록을 채우는 방식도 같아서, 항목을 숨기는 대신 매번
비우고 새로 담는다(GridListWidget이 폭으로 열을 나누므로 즐겨찾기는 끝에
relayout까지 부른다).

**한 모듈에 둔 이유는 둘이 실제로 맞물려 있기 때문이다.** 즐겨찾기 신규 확인은
받아 온 회차 중 무엇이 새것인지를 history_store에 물어서 가른다. 나눠 놓으면
그 한 줄 때문에 두 모듈이 서로를 부르게 된다. 코드량으로도 기록 31줄 /
즐겨찾기 89줄이라 파일을 가를 만큼 무겁지 않다.

즐겨찾기 쪽이 훨씬 두꺼운 것은 확인 흐름 때문이다. 기록은 보여 주고 지우는 것이
전부지만, 즐겨찾기는 등록·확인·신규 회차 처리까지 이어진다.

창 참조는 생성자로 받는다. 대기열에 넣는 일은 창의 _request_add_task 하나로
모으고 여기서 직접 하지 않는다 — 중복 확인 창이 그 안에 있어, 우회하면 이미
받은 회차를 묻지도 않고 다시 받는다.
"""

import os
import webbrowser
from typing import Dict, List

from PyQt6.QtWidgets import QListWidgetItem, QMessageBox
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QCursor, QGuiApplication

from src.message import confirm
from src.widgets import FavoriteItemWidget, HistoryItemWidget, RoundedMenu


class LibraryController:
    """기록·즐겨찾기 두 목록을 그리고 거르는 조작 묶음."""

    HISTORY_MAX_DISPLAY = 100
    """기록 탭에 한 번에 그리는 최대 개수. 나머지는 검색으로 찾는다.

    수백 개를 한꺼번에 카드로 만들면 탭을 여는 순간 멈칫한다."""

    MAX_FAVORITES = 20
    """즐겨찾기에 담을 수 있는 최대 시리즈 수.

    전부 자동 확인 대상이라, 늘어나면 시작할 때 도는 분석도 그만큼 길어진다."""

    FAV_AUTO_ADD_LIMIT = 2
    """말없이 대기열에 넣어도 되는 신규 회차 수.

    이보다 많으면 선택 창을 띄운다. 50~70개짜리 시리즈가 확인 없이 쏟아지면
    정작 지금 받고 싶은 영상이 그 뒤로 밀린다."""

    def __init__(self, window):
        self.window = window

    def refresh_history_list(self):
        window = self.window
        search_term = window.ui.history_search_input.text().lower(); sort_index = window.ui.history_sort_combo.currentIndex()
        all_entries = window.history_store.sorted_entries()
        if search_term: entries_to_show = [(url, meta) for url, meta in all_entries if search_term in meta.get('title', '').lower() or search_term in url.lower()]
        else: entries_to_show = all_entries
        if sort_index == 1: entries_to_show.sort(key=lambda item: item[1].get('title', ''))

        total_count = len(entries_to_show)
        display_entries = entries_to_show[:self.HISTORY_MAX_DISPLAY]

        window.ui.history_empty.set_filtered(bool(search_term))
        window.ui.history_list.clear()
        for url, meta in display_entries:
            item = QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole, url)
            if meta.get("series_id") or meta.get("thumbnail_url"):
                widget = HistoryItemWidget(url, meta, window.config.get("theme", "light")); item.setSizeHint(widget.sizeHint())
                window.ui.history_list.addItem(item); window.ui.history_list.setItemWidget(item, widget)
            else:
                title = meta.get("title", "(제목 없음)"); date = meta.get("date", "")
                item.setText(f"{title}  •  {date}\n{url}"); item.setSizeHint(QSize(0, 90)); window.ui.history_list.addItem(item)

        if total_count > self.HISTORY_MAX_DISPLAY:
            info_item = QListWidgetItem(f"... 외 {total_count - self.HISTORY_MAX_DISPLAY}개의 이전 기록이 있습니다. (검색하여 찾을 수 있습니다)")
            info_item.setFlags(Qt.ItemFlag.NoItemFlags); info_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            window.ui.history_list.addItem(info_item)

    def show_history_menu(self, pos):
        window = self.window
        item = window.ui.history_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        menu.addAction("URL 복사", lambda: QGuiApplication.clipboard().setText(url)); menu.addAction("다시 다운로드", lambda: window._request_add_task(url))
        menu.addAction("기록에서 제거", lambda: self.remove_from_history(url)); menu.exec(QCursor.pos())

    def remove_from_history(self, url: str):
        window = self.window
        window.history_store.remove(url); window.history_store.save(); self.refresh_history_list(); window.append_log(f"[알림] 기록에서 제거됨: {url}")

    def refresh_fav_list(self):
        """검색어에 걸리는 즐겨찾기만 다시 그린다.

        기록 탭과 같은 방식이다. 항목을 숨기는 대신 목록을 새로 채운다.
        GridListWidget은 항목 폭으로 열을 나누므로, 다 채운 뒤 relayout()으로
        지금 폭에 맞는 크기를 다시 먹여야 열이 어긋나지 않는다.
        """
        window = self.window
        search_term = window.ui.fav_search_input.text().strip().lower()
        window.ui.fav_empty.set_filtered(bool(search_term))
        window.ui.fav_list.clear()
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
            QMessageBox.information(window, "즐겨찾기 개수 초과",
                                      f"즐겨찾기는 최대 {self.MAX_FAVORITES}개까지 추가할 수 있습니다.\n\n"
                                      "새로운 시리즈를 추가하려면, 시청이 종료되었거나\n"
                                      "자주 확인하지 않는 시리즈를 목록에서 먼저 삭제해주세요.")
            return

        url = window.ui.fav_input.text().strip()
        if not url or "/series/" not in url:
            QMessageBox.information(window, "알림", "유효한 TVer 시리즈 URL을 입력하세요.")
            return
        if window.fav_store.exists(url):
            QMessageBox.information(window, "알림", "이미 즐겨찾기에 등록된 시리즈입니다.")
            return

        window.fav_store.add(url)
        window.ui.fav_input.clear()
        window.ui.fav_search_input.clear()
        self.refresh_fav_list()
        window.append_log(f"[즐겨찾기] 추가됨: {url}. 시리즈 제목 확인 중...")
        window.series_parser.parse('fav-add-check', [url])

    def remove_selected_favorite(self):
        window = self.window
        selected_items = window.ui.fav_list.selectedItems()
        if not selected_items: QMessageBox.information(window, "알림", "삭제할 항목을 목록에서 선택하세요."); return
        if confirm(window, "삭제 확인", f"{len(selected_items)}개의 항목을 삭제할까요?",
                   icon_name="nav_cache", color_key="danger",
                   theme=window.config.get("theme", "light")):
            for item in selected_items:
                url = item.data(Qt.ItemDataRole.UserRole); window.fav_store.remove(url); window.append_log(f"[즐겨찾기] 삭제: {url}")
            self.refresh_fav_list()

    def check_all_favorites(self):
        window = self.window
        folder = window.config.get("download_folder")
        if not folder or not os.path.isdir(folder): window.append_log("[알림] 다운로드 폴더가 설정되지 않아 시작 시 즐겨찾기 자동 확인을 건너뜁니다."); return
        urls = window.fav_store.list_series()
        if not urls:
            if window.sender() == window.ui.fav_chk_btn: QMessageBox.information(window, "알림", "등록된 즐겨찾기가 없습니다.")
            return
        window.append_log(f"[즐겨찾기] 전체 확인 시작 ({len(urls)}개 시리즈)"); window.series_parser.parse('fav-check', urls); window.ui.tabs.setCurrentIndex(0)

    def show_fav_menu(self, pos):
        window = self.window
        item = window.ui.fav_list.itemAt(pos)
        if not item: return
        url = item.data(Qt.ItemDataRole.UserRole); menu = RoundedMenu()
        def check_this_series(): window.series_parser.parse('fav-check', [url]); window.ui.tabs.setCurrentIndex(0)
        menu.addAction("이 시리즈 확인", check_this_series); menu.addAction("브라우저에서 열기", lambda: webbrowser.open(url))
        menu.addAction("삭제", lambda: self.remove_favorite(url)); menu.exec(QCursor.pos())

    def remove_favorite(self, url: str):
        window = self.window
        window.fav_store.remove(url); self.refresh_fav_list(); window.append_log(f"[즐겨찾기] 삭제: {url}")

    def on_fav_check_parsed(self, series_url: str, series_title: str, episode_info: List[Dict[str, str]]):
        """확인이 끝난 즐겨찾기 시리즈에서 신규 회차를 가려낸다.

        신규가 FAV_AUTO_ADD_LIMIT 이하면 그냥 받고, 그보다 많으면 선택 창을 띄운다.
        회차가 수십 개인 시리즈를 확인 없이 대기열에 통째로 쏟아부으면 정작 지금
        받고 싶은 영상이 그 뒤에 밀린다.
        """
        window = self.window
        window.fav_store.touch_last_check(series_url, series_title)
        self.refresh_fav_list()
        label = series_title or series_url
        new_episodes = [ep for ep in episode_info if not window.history_store.exists(ep['url'])]
        if not new_episodes:
            return
        if len(new_episodes) <= self.FAV_AUTO_ADD_LIMIT:
            added_count = 0
            for episode in new_episodes:
                if window._request_add_task(episode['url']): added_count += 1
            if added_count:
                window.append_log(f"[즐겨찾기] '{label}'에서 신규 에피소드 {added_count}개를 추가했습니다.")
            return
        window.append_log(f"[즐겨찾기] '{label}'에서 신규 에피소드 {len(new_episodes)}개를 찾았습니다. 받을 항목을 선택하세요.")
        window._add_from_selection(new_episodes, f"[즐겨찾기] '{label}'에서")

    def on_fav_add_check_parsed(self, series_url: str, series_title: str):
        """즐겨찾기에 갓 담은 시리즈의 제목을 받아 적는다.

        제목만 물어보는 분석이라 회차 목록은 오지 않는다. 못 가져와도 등록 자체는
        이미 끝났으므로 되돌리지 않고 알리기만 한다.
        """
        window = self.window
        if series_title:
            window.fav_store.touch_last_check(series_url, series_title)
            self.refresh_fav_list()
            window.append_log(f"[즐겨찾기] 시리즈 제목 업데이트: {series_title}")
        else:
            window.append_log(f"[알림] 즐겨찾기 추가 시 '{series_url}'의 제목을 가져오지 못했습니다.")
