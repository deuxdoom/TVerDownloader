# src/series_parser.py
# 수정: config 객체를 생성자에서 받고, update_config 메서드 추가
#      _run_next에서 스레드 생성 시 exclude_keywords를 config에서 읽어 전달

from typing import List, Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.series_parse_thread import SeriesParseThread

class SeriesParser(QObject):
    """
    여러 출처의 시리즈 URL 분석 요청을 큐로 관리하고,
    SeriesParseThread를 이용해 순차적으로 처리하는 관리자 클래스.
    """
    log = pyqtSignal(str, str) 
    finished = pyqtSignal(str, str, list)

    def __init__(self, ytdlp_path: str, config: Dict, parent=None): # ✅ config 추가
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.config = config # ✅ config 저장
        self._queue: List[Tuple[str, str]] = []  # [(context, url), ...]
        self._thread: Optional[SeriesParseThread] = None
        self._current_context: str = ""
        self._current_url: str = ""

    def set_ytdlp_path(self, path: str):
        self.ytdlp_path = path

    def update_config(self, config: Dict): # ✅ config 업데이트 메서드 추가
        self.config = config

    def parse(self, context: str, urls: List[str]):
        """
        분석할 URL 목록을 큐에 추가하고, 실행 가능한 경우 다음 작업을 시작합니다.
        """
        if not self.ytdlp_path:
            self.log.emit(context, "[오류] yt-dlp 경로가 설정되지 않아 시리즈를 분석할 수 없습니다.")
            return

        initial_count = len(self._queue)
        for url in urls:
            self._queue.append((context, url))
        
        if initial_count == 0 and self._queue:
            self._run_next()

    def _run_next(self):
        """큐에서 다음 작업을 꺼내 스레드를 실행합니다."""
        if self._thread is not None or not self._queue:
            return

        self._current_context, self._current_url = self._queue.pop(0)
        
        # ✅ config에서 제외 키워드를 읽어 스레드로 전달
        exclude_keywords = self.config.get("series_exclude_keywords", [])
        self._thread = SeriesParseThread(self._current_url, self.ytdlp_path, exclude_keywords)
        
        self._thread.log.connect(lambda msg: self.log.emit(self._current_context, msg))
        self._thread.finished.connect(self._on_parse_finished)
        self._thread.start()

    def _on_parse_finished(self, episode_urls: List[str]):
        """스레드 완료 시 결과를 finished 시그널로 보내고 다음 작업을 시작합니다."""
        self.finished.emit(self._current_context, self._current_url, episode_urls or [])
        
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        
        self._run_next()