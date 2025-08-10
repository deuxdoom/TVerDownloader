# src/threads/series_parse_thread.py
# 목적: 단일 시리즈 URL에서 포함된 모든 에피소드 URL 목록을 추출하는 스레드

import subprocess
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class SeriesParseThread(QThread):
    """시리즈 URL을 받아 하위 에피소드 URL 리스트를 반환하는 스레드."""
    log = pyqtSignal(str)
    finished = pyqtSignal(list)  # List[str]

    def __init__(self, series_url: str, ytdlp_exe_path: str, parent=None):
        super().__init__(parent)
        self.series_url = series_url
        self.ytdlp_exe_path = ytdlp_exe_path

    def run(self):
        try:
            self.log.emit(f"[시리즈] 분석 중: {self.series_url}")
            command = [
                self.ytdlp_exe_path,
                "--flat-playlist",
                "--print", "%(url)s\t%(title)s",
                "--skip-download",
                "--no-warnings",
                self.series_url,
            ]
            startupinfo = get_startupinfo()
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            out, err = proc.communicate()
            if proc.returncode != 0:
                self.log.emit(f"[오류] 시리즈 분석 실패:\n{(err or '').strip()}")
                self.finished.emit([])
                return

            lines = [l for l in (out or "").splitlines() if "\t" in l]
            pairs = [l.split("\t", 1) for l in lines]
            final_urls: List[str] = []
            
            # TVer 시리즈 목록에는 종종 예고편('予告')이 포함되므로 제외
            self.log.emit(f"시리즈에서 {len(pairs)}개의 항목을 찾았습니다. 예고편 제외 처리 중...")
            for url, title in pairs:
                if "予告" in (title or ""):
                    self.log.emit(f" -> 예고편 제외: {title}")
                    continue
                final_urls.append(url.strip())
                
            self.log.emit(f"최종 {len(final_urls)}개 에피소드 URL 추출 완료.")
            self.finished.emit(final_urls)
        except Exception as e:
            self.log.emit(f"[오류] 시리즈 분석 중 예외: {e}")
            self.finished.emit([])