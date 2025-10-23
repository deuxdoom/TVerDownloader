# src/threads/series_parse_thread.py
# 수정:
# - 생성자에서 exclude_keywords 리스트를 받음
# - _is_excluded 헬퍼 메서드 추가 (대소문자 무시)
# - _parse_entries, _parse_flat_output에서 하드코딩된 "予告" 대신 _is_excluded 사용

import subprocess
import json
from typing import List, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils import get_startupinfo

class SeriesParseThread(QThread):
    """시리즈 URL을 받아 하위 에피소드 정보(딕셔너리) 리스트를 반환하는 스레드."""
    log = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, series_url: str, ytdlp_exe_path: str, exclude_keywords: List[str], parent=None): # ✅ exclude_keywords 추가
        super().__init__(parent)
        self.series_url = series_url
        self.ytdlp_exe_path = ytdlp_exe_path
        # ✅ 제외 키워드를 소문자로 정규화하여 저장 (대소문자 무시 비교용)
        self.exclude_keywords = [k.lower() for k in exclude_keywords if k.strip()]

    def _is_excluded(self, title: str) -> bool:
        """ ✅ 제목이 제외 키워드를 포함하는지 확인 (대소문자 무시)"""
        if not self.exclude_keywords:
            return False
        title_lower = title.lower()
        for keyword in self.exclude_keywords:
            if keyword in title_lower:
                return True
        return False

    def _parse_entries(self, entries: list) -> List[Dict[str, str]]:
        """메타데이터 목록에서 필요한 정보를 추출합니다."""
        results: List[Dict[str, str]] = []
        for meta in entries:
            if not isinstance(meta, dict): continue
            url = meta.get("webpage_url") or meta.get("url")
            title = meta.get("title", "제목 없음")
            thumbnail_url = meta.get("thumbnail")

            # ✅ 하드코딩된 "予告" 대신 _is_excluded 헬퍼 메서드 사용
            if url and title and not self._is_excluded(title):
                results.append({
                    "url": url.strip(),
                    "title": title.strip(),
                    "thumbnail_url": thumbnail_url or ""
                })
        return results

    def _parse_json_output(self, out: str) -> List[Dict[str, str]]:
        """JSON 출력을 파싱하여 에피소드 정보 목록을 반환합니다."""
        try:
            data = json.loads(out)
            if isinstance(data, dict) and "entries" in data:
                return self._parse_entries(data.get("entries") or [])
            else:
                return self._parse_entries([data])
        except json.JSONDecodeError:
            entries = []
            for line in (out or "").splitlines():
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, KeyError): continue
            return self._parse_entries(entries)

    def _parse_flat_output(self, out: str) -> List[Dict[str, str]]:
        """--flat-playlist 출력을 파싱합니다. (썸네일 정보 없음)"""
        results: List[Dict[str, str]] = []
        lines = [l for l in (out or "").splitlines() if "\t" in l]
        for line in lines:
            try:
                url, title = line.split("\t", 1)
                 # ✅ 하드코딩된 "予告" 대신 _is_excluded 헬퍼 메서드 사용
                if not self._is_excluded(title or ""):
                    results.append({"url": url.strip(), "title": title.strip(), "thumbnail_url": ""})
            except ValueError: continue
        return results

    def run(self):
        try:
            self.log.emit(f"[시리즈] 분석 중 (1/2): {self.series_url}")
            command1 = [self.ytdlp_exe_path, "-J", "--skip-download", "--no-warnings", self.series_url]
            startupinfo = get_startupinfo()
            proc1 = subprocess.Popen(
                command1, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                startupinfo=startupinfo, text=True, encoding="utf-8", errors="ignore"
            )
            out1, err1 = proc1.communicate()

            if proc1.returncode != 0:
                self.log.emit(f"[오류] 시리즈 1차 분석 실패:\n{(err1 or '').strip()}"); self.finished.emit([]); return

            episodes = self._parse_json_output(out1)

            if not episodes:
                self.log.emit("[시리즈] 1차 분석 결과 없음. 2차 분석 시도...")
                command2 = [self.ytdlp_exe_path, "--flat-playlist", "--print", "%(url)s\t%(title)s", "--skip-download", "--no-warnings", self.series_url]
                proc2 = subprocess.Popen(
                    command2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    startupinfo=startupinfo, text=True, encoding="utf-8", errors="ignore"
                )
                out2, err2 = proc2.communicate()

                if proc2.returncode != 0:
                    self.log.emit(f"[오류] 시리즈 2차 분석 실패:\n{(err2 or '').strip()}"); self.finished.emit([]); return
                
                episodes = self._parse_flat_output(out2)
                if not episodes and err2: self.log.emit(f"[진단] 2차 분석 결과 없음. 오류 스트림: {(err2 or '없음').strip()}")

            self.log.emit(f"최종 {len(episodes)}개 에피소드 정보 추출 완료.")
            self.finished.emit(episodes)
        except Exception as e:
            self.log.emit(f"[오류] 시리즈 분석 중 예외: {e}"); self.finished.emit([])