import json
from typing import List, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from src.threads import ytdlp_run

class SeriesParseThread(QThread):
    """시리즈 URL을 받아 하위 에피소드 정보(딕셔너리) 리스트를 반환하는 스레드."""
    log = pyqtSignal(str)
    finished = pyqtSignal(str, list)

    TITLE_ONLY_TIMEOUT = 60
    PARSE_TIMEOUT = 300
    """전체 회차를 훑는 분석의 제한 시간. 72화 기준 61초라 넉넉히 잡는다.

    없이 두면 yt-dlp가 응답을 기다리며 멈춰 있을 때 즐겨찾기 확인 대기열 전체가
    그 자리에 선다. 한 시리즈가 막히더라도 나머지는 이어져야 한다.
    """

    def __init__(self, series_url: str, ytdlp_exe_path: str, exclude_keywords: List[str],
                 title_only: bool = False, parent=None):
        super().__init__(parent)
        self.series_url = series_url
        self.ytdlp_exe_path = ytdlp_exe_path
        self.exclude_keywords = [k.lower() for k in exclude_keywords if k.strip()]
        self.title_only = title_only

    def _is_excluded(self, title: str) -> bool:
        if not self.exclude_keywords:
            return False
        title_lower = title.lower()
        for keyword in self.exclude_keywords:
            if keyword in title_lower:
                return True
        return False

    def _parse_entries(self, entries: list) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for meta in entries:
            if not isinstance(meta, dict): continue
            url = meta.get("webpage_url") or meta.get("url")
            title = meta.get("title", "제목 없음")
            thumbnail_url = meta.get("thumbnail")
            if url and title and not self._is_excluded(title):
                results.append({
                    "url": url.strip(),
                    "title": title.strip(),
                    "thumbnail_url": thumbnail_url or ""
                })
        return results

    def _parse_json_output(self, out: str) -> List[Dict[str, str]]:
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
        results: List[Dict[str, str]] = []
        lines = [l for l in (out or "").splitlines() if "\t" in l]
        for line in lines:
            try:
                url, title = line.split("\t", 1)
                if not self._is_excluded(title or ""):
                    results.append({"url": url.strip(), "title": title.strip(), "thumbnail_url": ""})
            except ValueError: continue
        return results

    def _run_title_only(self):
        """시리즈 제목만 확인한다.

        --flat-playlist는 회차를 하나씩 열어 보지 않는다. 72화짜리 시리즈에서
        전체 메타데이터는 60초가 걸리는데 이 방식은 4초면 끝난다. 즐겨찾기에 막
        넣은 시리즈는 제목만 있으면 되고, 회차 목록은 '신규 영상 확인'을 누르거나
        다음 실행 때 어차피 다시 훑는다.
        """
        self.log.emit(f"[시리즈] 제목 확인 중: {self.series_url}")
        command = [self.ytdlp_exe_path, "--flat-playlist", "--playlist-items", "1", "-J", "--skip-download",
                   *ytdlp_run.network_options(), self.series_url]
        ok, out, err = ytdlp_run.run(command, self.TITLE_ONLY_TIMEOUT, "시리즈 제목 확인", self.log.emit)
        if not ok:
            self.log.emit(f"[오류] 시리즈 제목 확인 실패:\n{(err or '').strip()}")
            self.finished.emit("", [])
            return

        try:
            data = json.loads(out)
            series_title = data.get("playlist_title") or data.get("title", "")
        except json.JSONDecodeError:
            series_title = ""
        self.finished.emit(series_title, [])

    def run(self):
        try:
            if self.title_only:
                self._run_title_only()
                return
            self.log.emit(f"[시리즈] 분석 중 (1/2): {self.series_url}")
            command1 = [self.ytdlp_exe_path, "-J", "--skip-download",
                        *ytdlp_run.network_options(), self.series_url]
            ok1, out1, err1 = ytdlp_run.run(command1, self.PARSE_TIMEOUT, "시리즈 1차 분석", self.log.emit)

            series_title = ""
            episodes = []

            if ok1:
                try:
                    data = json.loads(out1)
                    series_title = data.get("playlist_title") or data.get("title", "")
                except json.JSONDecodeError:
                    pass
                episodes = self._parse_json_output(out1)
            else:
                self.log.emit(f"[오류] 시리즈 1차 분석 실패:\n{(err1 or '').strip()}");
                self.finished.emit("", []); return

            if not episodes:
                self.log.emit("[시리즈] 1차 분석 결과 없음. 2차 분석 시도...")
                command2 = [self.ytdlp_exe_path, "--flat-playlist",
                            "--print", "%(url)s\t%(title)s", "--skip-download",
                            *ytdlp_run.network_options(), self.series_url]
                ok2, out2, err2 = ytdlp_run.run(command2, self.PARSE_TIMEOUT, "시리즈 2차 분석", self.log.emit)

                if not ok2:
                    self.log.emit(f"[오류] 시리즈 2차 분석 실패:\n{(err2 or '').strip()}");
                    self.finished.emit(series_title, []); return

                episodes = self._parse_flat_output(out2)
                if not episodes and err2: self.log.emit(f"[진단] 2차 분석 결과 없음. 오류 스트림: {(err2 or '없음').strip()}")

            self.log.emit(f"최종 {len(episodes)}개 에피소드 정보 추출 완료.")
            self.finished.emit(series_title, episodes)
        except Exception as e:
            self.log.emit(f"[오류] 시리즈 분석 중 예외: {e}");
            self.finished.emit("", [])
