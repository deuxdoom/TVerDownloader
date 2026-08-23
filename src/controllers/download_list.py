"""다운로드 목록 탭의 조작을 맡는다 - 카드 넣고 빼기, 중지·제거, 우클릭 메뉴, 재다운로드.

창에서 떼어낸 것은 이것들이 하나같이 같은 셋(목록의 행, 그 행의 카드, 그 URL의 대기열
상태)을 함께 봐야 하기 때문이다. 대기열 상태는 반드시 DownloadManager의
is_busy/is_queued/is_pending을 거친다 - 자료구조를 직접 보면 변환만 남은 항목이 새어 나간다.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtWidgets import QListWidgetItem, QFileDialog, QWidget
from PyQt6.QtGui import QCursor

from src.utils import open_file_location, ERROR_STATUSES, FILENAME_TITLE_MAX_LENGTH
from src.widgets import DownloadItemWidget, RoundedMenu


class DownloadListController:
    """다운로드 목록 위젯 하나를 맡아 보는 조작 묶음."""

    def __init__(self, window):
        self.window = window

    def add_item_widget(self, url: str):
        window = self.window
        existing = self.find_item_widget(url)
        if isinstance(existing, DownloadItemWidget):
            existing.reset_for_retry()
            return
        item = QListWidgetItem(); widget = DownloadItemWidget(url, window.config.get("theme", "light"))
        widget.play_requested.connect(window.play_file)
        widget.open_folder_requested.connect(open_file_location)
        item.setSizeHint(widget.sizeHint())
        window.ui.download_list.insertItem(0, item); window.ui.download_list.setItemWidget(item, widget)

    def find_item_widget(self, url: str) -> Optional[QWidget]:
        download_list = self.window.ui.download_list
        for i in range(download_list.count()):
            item = download_list.item(i); widget = download_list.itemWidget(item)
            if hasattr(widget, 'url') and widget.url == url: return widget
        return None

    def update_item_widget(self, url: str, payload: Dict):
        widget = self.find_item_widget(url)
        if isinstance(widget, DownloadItemWidget): widget.update_progress(payload)

    def delete_selected(self):
        """선택한 카드를 목록에서 지운다. 진행 중인 것은 남긴다.

        카드만 지우면 멈출 방법이 사라진 채로 다운로드나 변환이 계속 돈다. 중지까지
        하려면 '선택 항목 취소' 쪽이다.
        """
        window = self.window
        selected_items = window.ui.download_list.selectedItems()
        if not selected_items: return
        rows_to_delete = sorted([window.ui.download_list.row(item) for item in selected_items], reverse=True)
        for row in rows_to_delete:
            item = window.ui.download_list.item(row); widget = window.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget): continue
            url = widget.url
            if window.download_manager.is_busy(url): continue
            if window.download_manager.is_queued(url): window.download_manager.remove_task_from_queue(url)
            self.remove_row(row)

    def sync_selection_styles(self, list_widget):
        """목록 위젯 안의 항목들에게 자신의 선택 여부를 알린다."""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if hasattr(widget, "set_selected"):
                widget.set_selected(item.isSelected())

    def remove_row(self, row: int):
        """카드를 목록에서 뺀다. 애니메이션과 콜백을 먼저 끊어야 리소스가 남지 않는다.

        takeItem은 카드를 deleteLater로 미루고, 그 사이에도 걸어 둔 썸네일 요청과 진행
        애니메이션이 그대로 돈다.
        """
        item = self.window.ui.download_list.item(row)
        if item is None:
            return
        widget = self.window.ui.download_list.itemWidget(item)
        if isinstance(widget, DownloadItemWidget):
            widget.cleanup()
        self.window.ui.download_list.takeItem(row)

    def cancel_selected(self):
        """선택한 항목을 상태에 맞게 정리한다.

        진행 중이면 중지하고 카드는 남긴다(재다운로드할 수 있다). 대기 중이면 대기열에서
        빼고 목록에서도 지운다. 이미 끝난 것은 '완료 항목 삭제'가 맡는다.
        """
        window = self.window
        selected_items = window.ui.download_list.selectedItems()
        if not selected_items:
            return
        rows = sorted((window.ui.download_list.row(item) for item in selected_items), reverse=True)
        stopped = removed = 0
        for row in rows:
            item = window.ui.download_list.item(row)
            widget = window.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget):
                continue
            url = widget.url
            if window.download_manager.is_busy(url):
                window.download_manager.stop_task(url)
                stopped += 1
            elif window.download_manager.is_queued(url):
                if window.download_manager.remove_task_from_queue(url):
                    self.remove_row(row)
                    removed += 1
        parts = []
        if stopped: parts.append(f"진행 중 {stopped}개 중지")
        if removed: parts.append(f"대기 중 {removed}개 제거")
        window.append_log("[대기열] " + (", ".join(parts) if parts
                                        else "선택한 항목 중 중지하거나 뺄 것이 없습니다."))

    def sync_cancel_button(self):
        self.window.ui.cancel_selected_button.setEnabled(bool(self.window.ui.download_list.selectedItems()))

    def clear_completed(self):
        """끝난 카드만 걷어낸다. 아직 끝나지 않은 것은 무엇이든 남긴다.

        '끝났다'의 반대를 다운로드 중으로만 보면 변환 중인 항목이 완료로 새어 나가,
        목록에서 사라진 뒤에도 ffmpeg가 계속 돈다.
        """
        window = self.window
        for i in range(window.ui.download_list.count() - 1, -1, -1):
            item = window.ui.download_list.item(i); widget = window.ui.download_list.itemWidget(item)
            if not isinstance(widget, DownloadItemWidget): continue
            if not window.download_manager.is_pending(widget.url): self.remove_row(i)

    def show_context_menu(self, pos):
        window = self.window
        item = window.ui.download_list.itemAt(pos)
        if not item: return
        widget = window.ui.download_list.itemWidget(item)
        if not isinstance(widget, DownloadItemWidget): return
        selected = window.ui.download_list.selectedItems()
        if len(selected) > 1 and item in selected:
            menu = RoundedMenu()
            menu.addAction(f"선택한 {len(selected)}개 중지 · 대기열에서 제거",
                           self.cancel_selected)
            menu.addAction(f"선택한 {len(selected)}개 목록에서 삭제",
                           self.delete_selected)
            menu.exec(QCursor.pos())
            return
        url = widget.url; menu = RoundedMenu()
        if window.download_manager.is_busy(url):
            menu.addAction("중지", lambda: window.download_manager.stop_task(url))
        elif window.download_manager.is_queued(url):
            def remove_from_queue():
                if window.download_manager.remove_task_from_queue(url): self.remove_row(window.ui.download_list.row(item))
            menu.addAction("대기열에서 제거", remove_from_queue)
        else:
            if widget.status in ERROR_STATUSES:
                menu.addAction("재다운로드", lambda: self.retry_download(url))
            menu.addAction("목록에서 삭제", lambda: self.remove_row(window.ui.download_list.row(item)))
        self._add_file_actions(menu, widget)
        menu.exec(QCursor.pos())

    def _add_file_actions(self, menu, widget):
        """파일에 관한 항목들을 구분선 뒤에 모아 붙인다.

        위쪽은 이 줄을 대기열에서 어떻게 할지, 아래쪽은 받아 둔 것으로 무엇을 할지다.
        할 수 있는 것만 붙이고, 구분선은 뒤에 실제로 붙은 것이 있을 때만 긋는다.
        """
        actions = []
        if widget.thumbnail_pixmap() is not None:
            actions.append(("썸네일 다운로드", lambda: self._save_thumbnail(widget)))
        if widget.final_filepath and os.path.exists(widget.final_filepath):
            actions.append(("파일 재생", lambda: self.window.play_file(widget.final_filepath)))
            actions.append(("파일 위치 열기", lambda: open_file_location(widget.final_filepath)))
        if not actions:
            return
        menu.addSeparator()
        for label, handler in actions:
            menu.addAction(label, handler)

    THUMBNAIL_SAVE_FILTER = "PNG 이미지 (*.png);;JPEG 이미지 (*.jpg *.jpeg)"

    def _save_thumbnail(self, widget):
        """카드에 걸린 썸네일 원본을 파일로 저장한다.

        기본 이름은 받아 둔 영상 파일 이름을 따라간다 - 나란히 두었을 때 어느 영상의
        그림인지 알 수 있고, 이미 파일 이름으로 쓸 수 있는 글자만 남아 있다.
        """
        window = self.window
        pixmap = widget.thumbnail_pixmap()
        if pixmap is None:
            window.append_log("[알림] 저장할 썸네일이 아직 없습니다.")
            return
        if widget.final_filepath:
            suggested = Path(widget.final_filepath).with_suffix(".png").name
        else:
            suggested = self._safe_filename(widget.title_label.text()) + ".png"
        folder = window.config.get("download_folder") or ""
        path, _ = QFileDialog.getSaveFileName(
            window, "썸네일 저장", os.path.join(folder, suggested), self.THUMBNAIL_SAVE_FILTER)
        if not path:
            return
        if pixmap.save(path):
            window.append_log(f"[성공] 썸네일을 저장했습니다: {path}")
        else:
            window.append_log(f"[오류] 썸네일을 저장하지 못했습니다: {path}")

    FILENAME_FORBIDDEN = '<>:"/\\|?*'
    """윈도우가 파일 이름에 허용하지 않는 글자."""

    @staticmethod
    def _safe_filename(text: str) -> str:
        """제목을 파일 이름으로 쓸 수 있게 다듬는다. 비면 기본 이름을 준다."""
        cleaned = "".join("_" if ch in DownloadListController.FILENAME_FORBIDDEN or ord(ch) < 32 else ch
                          for ch in text).strip(" .")
        return cleaned[:FILENAME_TITLE_MAX_LENGTH] or "thumbnail"

    def retry_download(self, url: str):
        window = self.window
        if window.download_manager.is_pending(url):
            return
        if not window._ensure_download_folder():
            window.append_log("[알림] 다운로드 폴더가 설정되지 않아 재다운로드를 취소했습니다.")
            return
        window.download_manager.reset_for_redownload(url)
        widget = self.find_item_widget(url)
        if isinstance(widget, DownloadItemWidget):
            widget.reset_for_retry()
        window.download_manager.add_task(url)
