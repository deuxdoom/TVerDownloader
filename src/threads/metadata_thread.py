"""대기열에 서 있는 항목의 제목·표지 그림을 미리 물어보는 스레드.

**DownloadThread._get_metadata와 같은 질의를 같은 조건으로 던진다.** 받아 온 것을 그대로
DownloadThread에 넘겨 쓰므로(preloaded_metadata) 미리 물어본 항목은 받을 때 다시 묻지
않는다 - 미리 묻기가 통신을 늘리는 것이 아니라 앞당길 뿐이도록 하는 것이 요점이다.

실패는 조용히 넘긴다. 여기서 못 가져와도 받을 때 DownloadThread가 제 몫으로 다시 묻는다.
"""

import json
import subprocess
import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.i18n import t
from src.threads import ytdlp_run


class MetadataThread(QThread):
    loaded = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    TIMEOUT = 60
    """DownloadThread.METADATA_TIMEOUT과 같은 값.

    여기만 짧게 잡으면 받을 때는 성공하는 항목이 미리 묻기에서만 실패해, 화면에 있고
    없고가 통신 상태에 따라 들쭉날쭉해진다.
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

        플래그와 프로세스를 자물쇠로 묶는 것은 ConversionThread.stop과 같은 이유다 -
        start() 직후의 중단은 죽일 대상이 아직 없어, 그 사이에 프로세스가 뜨면 플래그만
        선 채로 질의가 끝까지 돌아간다.
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
        ok, out, err = ytdlp_run.run(cmd, self.TIMEOUT, t("series_parse.metadata_label"),
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
            self.failed.emit(self.url, t("series_parse.metadata_unreadable"))
            return
        if not isinstance(metadata, dict):
            self.failed.emit(self.url, t("series_parse.metadata_malformed"))
            return
        self.loaded.emit(self.url, metadata)
