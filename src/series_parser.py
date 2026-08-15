from typing import List, Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.series_parse_thread import SeriesParseThread

class SeriesParser(QObject):
    log = pyqtSignal(str, str)
    finished = pyqtSignal(str, str, str, list)

    USER_CONTEXTS = ("single", "bulk", "fav-add-check")
    """사용자가 방금 요청한 분석. 배경으로 도는 즐겨찾기 확인보다 앞에 세운다."""

    TITLE_ONLY_CONTEXTS = ("fav-add-check",)
    """제목만 있으면 되는 분석. 회차 목록을 훑지 않아 몇 초 만에 끝난다."""

    def __init__(self, ytdlp_path: str, config: Dict, parent=None):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.config = config
        self._queue: List[Tuple[str, str]] = []
        self._thread: Optional[SeriesParseThread] = None
        self._current_context: str = ""
        self._current_url: str = ""

    def set_ytdlp_path(self, path: str):
        self.ytdlp_path = path

    def update_config(self, config: Dict):
        self.config = config

    def parse(self, context: str, urls: List[str]):
        """분석 대기열에 넣는다. 사용자 요청은 즐겨찾기 확인 앞으로 끼어든다.

        즐겨찾기를 여러 개 확인하는 중에는 대기열이 길어서, 그냥 뒤에 붙이면
        방금 붙여넣은 시리즈가 몇 분씩 밀린다. 사용자가 기다리는 쪽을 먼저 돌린다.
        """
        if not self.ytdlp_path:
            self.log.emit(context, "[오류] yt-dlp 경로가 설정되지 않아 시리즈를 분석할 수 없습니다.")
            return

        items = [(context, url) for url in urls]
        if context in self.USER_CONTEXTS:
            insert_at = 0
            while (insert_at < len(self._queue)
                   and self._queue[insert_at][0] in self.USER_CONTEXTS):
                insert_at += 1
            self._queue[insert_at:insert_at] = items
        else:
            self._queue.extend(items)

        self._run_next()

    def pending_count(self) -> int:
        """대기 중인 분석 건수(진행 중인 것은 제외)."""
        return len(self._queue)

    def _run_next(self):
        if self._thread is not None or not self._queue:
            return
        self._current_context, self._current_url = self._queue.pop(0)
        exclude_keywords = self.config.get("series_exclude_keywords", [])
        self._thread = SeriesParseThread(
            self._current_url, self.ytdlp_path, exclude_keywords,
            title_only=self._current_context in self.TITLE_ONLY_CONTEXTS)
        self._thread.log.connect(lambda msg: self.log.emit(self._current_context, msg))
        self._thread.finished.connect(self._on_parse_finished)
        self._thread.start()

    def _on_parse_finished(self, series_title: str, episode_urls: List[str]):
        """스레드 완료 시 결과를 finished 시그널로 보내고 다음 작업을 시작합니다."""
        self.finished.emit(self._current_context, self._current_url, series_title, episode_urls or [])

        if self._thread:
            self._thread.deleteLater()
            self._thread = None

        self._run_next()
