# src/series_parser.py
# 수정:
# - finished 시그널에 series_title 추가
# - _on_parse_finished에서 series_title을 받아 finished 시그널로 전달

from typing import List, Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.series_parse_thread import SeriesParseThread

class SeriesParser(QObject):
    log = pyqtSignal(str, str) 
    # ✅ finished 시그널 변경: (컨텍스트, 시리즈 URL, 시리즈 제목, 에피소드 리스트)
    finished = pyqtSignal(str, str, str, list)

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
        if not self.ytdlp_path:
            self.log.emit(context, "[오류] yt-dlp 경로가 설정되지 않아 시리즈를 분석할 수 없습니다.")
            return
        initial_count = len(self._queue)
        for url in urls:
            self._queue.append((context, url))
        if initial_count == 0 and self._queue:
            self._run_next()

    def _run_next(self):
        if self._thread is not None or not self._queue:
            return
        self._current_context, self._current_url = self._queue.pop(0)
        exclude_keywords = self.config.get("series_exclude_keywords", [])
        self._thread = SeriesParseThread(self._current_url, self.ytdlp_path, exclude_keywords)
        self._thread.log.connect(lambda msg: self.log.emit(self._current_context, msg))
        # ✅ _on_parse_finished 시그널 연결 (인자 개수 맞춤)
        self._thread.finished.connect(self._on_parse_finished)
        self._thread.start()

    # ✅ _on_parse_finished 시그 B: (시리즈 제목, 에피소드 URL 리스트)
    def _on_parse_finished(self, series_title: str, episode_urls: List[str]):
        """스레드 완료 시 결과를 finished 시그널로 보내고 다음 작업을 시작합니다."""
        # ✅ 시리즈 제목을 포함하여 emit
        self.finished.emit(self._current_context, self._current_url, series_title, episode_urls or [])
        
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        
        self._run_next()