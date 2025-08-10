# src/series_parser.py
# 목적: 다중/단일/즐겨찾기 등 모든 시리즈 URL 분석 요청을 받아 처리하고 결과를 반환

from typing import List, Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from src.threads.series_parse_thread import SeriesParseThread

class SeriesParser(QObject):
    """
    여러 출처의 시리즈 URL 분석 요청을 큐로 관리하고,
    SeriesParseThread를 이용해 순차적으로 처리하는 관리자 클래스.
    """
    # 시그널: (컨텍스트, 로그 메시지)
    log = pyqtSignal(str, str) 
    # 시그널: (컨텍스트, 원본 시리즈 URL, 찾은 에피소드 URL 리스트)
    finished = pyqtSignal(str, str, list)

    def __init__(self, ytdlp_path: str, parent=None):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self._queue: List[Tuple[str, str]] = []  # [(context, url), ...]
        self._thread: Optional[SeriesParseThread] = None
        self._current_context: str = ""
        self._current_url: str = ""

    def set_ytdlp_path(self, path: str):
        self.ytdlp_path = path

    def parse(self, context: str, urls: List[str]):
        """
        분석할 URL 목록을 큐에 추가하고, 실행 가능한 경우 다음 작업을 시작합니다.
        - context: 'bulk', 'single', 'fav-check' 등 작업 출처를 구분하는 문자열
        - urls: 분석할 시리즈 URL 리스트
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
        
        self._thread = SeriesParseThread(self._current_url, self.ytdlp_path)
        self._thread.log.connect(lambda msg: self.log.emit(self._current_context, msg))
        self._thread.finished.connect(self._on_parse_finished)
        self._thread.start()

    def _on_parse_finished(self, episode_urls: List[str]):
        """스레드 완료 시 결과를 finished 시그널로 보내고 다음 작업을 시작합니다."""
        self.finished.emit(self._current_context, self._current_url, episode_urls or [])
        
        # 스레드 정리 후 다음 작업으로
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        
        self._run_next()