"""대기열에 서 있는 항목의 제목·표지 그림을 미리 물어보는 스레드.

받기 시작해야 제목이 뜨던 것을 앞당긴다. 동시 다운로드 수를 넘긴 항목은
차례가 올 때까지 `제목 로딩 중…`과 빈 그림으로 남아 있어서, 열 개를 걸어 두면
그중 무엇이 무엇인지 주소로만 구별해야 했다.

**DownloadThread._get_metadata와 같은 질의를 같은 조건으로 던진다.** 받아 온
것을 그대로 DownloadThread에 넘겨 쓰므로(preloaded_metadata), 미리 물어본
항목은 받을 때 다시 묻지 않는다. 미리 묻기가 통신을 늘리는 것이 아니라
**앞당길 뿐이도록** 하는 것이 이 짜임의 요점이다.

실패는 조용히 넘긴다. 여기서 못 가져와도 받을 때 DownloadThread가 제 몫으로
다시 물어보므로, 다운로드 자체는 예전과 똑같이 굴러간다.
"""

import json
import subprocess
import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.threads import ytdlp_run


class MetadataThread(QThread):
    loaded = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    TIMEOUT = 60
    """DownloadThread.METADATA_TIMEOUT과 같은 값.

    같은 질의라 같은 만큼 기다린다. 여기만 짧게 잡으면 받을 때는 성공하는
    항목이 미리 물어보기에서만 실패해, 화면에 있고 없고가 통신 상태에 따라
    들쭉날쭉해진다.
    """

    def __init__(self, url: str, ytdlp_exe_path: str,
                 ignore_ssl_errors: bool = False, parent=None):
        super().__init__(parent)
        self.url = url
        self.ytdlp_exe_path = ytdlp_exe_path
        self.ignore_ssl_errors = ignore_ssl_errors
        self._process: Optional[subprocess.Popen] = None
        self._stop_flag = False
        self._process_lock = threading.Lock()

    def stop(self):
        """물어보던 것을 그만둔다.

        플래그를 세우는 일과 프로세스를 읽는 일을 자물쇠로 묶는 것은
        ConversionThread.stop과 같은 이유다. start() 직후에 들어온 중단은
        yt-dlp가 아직 뜨지 않아 죽일 대상이 없는데, 그 사이에 프로세스가 뜨면
        플래그만 선 채로 질의가 끝까지 돌아간다.
        """
        with self._process_lock:
            self._stop_flag = True
            proc = self._process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.kill()
        except OSError:
            pass

    def _on_spawn(self, proc: subprocess.Popen):
        """갓 뜬 프로세스를 붙잡아 둔다. 이미 그만두라고 했으면 그 자리에서 죽인다."""
        with self._process_lock:
            self._process = proc
            stopping = self._stop_flag
        if not stopping:
            return
        try:
            proc.kill()
        except OSError:
            pass

    def run(self):
        cmd = [self.ytdlp_exe_path, "-J", "--skip-download", *ytdlp_run.network_options()]
        if self.ignore_ssl_errors:
            cmd.append("--no-check-certificate")
        cmd.append(self.url)
        ok, out, err = ytdlp_run.run(cmd, self.TIMEOUT, "영상 정보 미리 확인",
                                     on_spawn=self._on_spawn,
                                     should_stop=lambda: self._stop_flag)
        if self._stop_flag:
            self.failed.emit(self.url, ytdlp_run.ABORTED)
            return
        if not ok:
            self.failed.emit(self.url, (err or "").strip())
            return
        try:
            metadata = json.loads(out)
        except json.JSONDecodeError:
            self.failed.emit(self.url, "영상 정보를 읽지 못했습니다.")
            return
        if not isinstance(metadata, dict):
            self.failed.emit(self.url, "영상 정보 형식이 예상과 다릅니다.")
            return
        self.loaded.emit(self.url, metadata)
