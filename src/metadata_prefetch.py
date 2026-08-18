"""대기열에 서 있는 항목의 정보를 미리 받아 두는 조정자.

**한 번에 하나씩만 물어본다.** 대기열에 스무 개가 있다고 스무 개를 한꺼번에
물으면, 그 순간 받고 있는 영상과 회선을 나눠 쓰게 된다. 조회 쪽이 느려지는
것으로 끝나지 않는다 — ytdlp_run 주석에 적힌 `Read timed out`이 바로 그
상황에서 났고, 그때 실패하는 것은 조회가 아니라 **받는 쪽**일 수도 있다.
줄 세워 하나씩 던지면 늘어나는 부하가 언제나 질의 하나뿐이다.

**받아 둔 것은 그대로 DownloadThread에 넘어간다**(take). 그래서 미리 묻기가
통신을 두 배로 늘리지 않고 앞당기기만 한다. 미리 묻지 못한 항목은 예전처럼
받기 직전에 DownloadThread가 스스로 묻는다.

**차례가 온 항목은 기다리지 않고 버린다.** 마침 그 항목을 묻고 있었다면 질의를
죽이고 받기부터 시작한다. 조회가 끝나기를 기다리면 미리 묻기가 다운로드를
늦추는 셈이 되는데, 그건 이 기능이 하려던 것과 정반대다.
"""

from typing import Callable, Dict, List, Optional

from PyQt6 import sip
from PyQt6.QtCore import QDeadlineTimer, QObject, pyqtSignal

from src.threads.metadata_thread import MetadataThread


class MetadataPrefetcher(QObject):
    """대기열 항목의 제목·표지 그림을 한 번에 하나씩 미리 받아 둔다."""

    loaded = pyqtSignal(str, dict)

    STOP_WAIT_MS = 2000
    """그만두라고 한 뒤 질의 스레드를 기다리는 시간.

    프로세스를 죽이면 곧바로 빠져나오므로 넉넉한 값이다. 그래도 기다리는 것은
    도는 QThread를 남긴 채 앱이 끝나면 그 자리에서 죽기 때문이다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ytdlp_path: Optional[str] = None
        self.ignore_ssl_errors = False
        self._pending: List[str] = []
        self._thread: Optional[MetadataThread] = None
        self._current: Optional[str] = None
        self._cache: Dict[str, dict] = {}
        self._retiring: List[MetadataThread] = []
        self._shutting_down = False
        self._is_wanted: Optional[Callable[[str], bool]] = None

    def set_ytdlp_path(self, path: str):
        """준비가 끝나 yt-dlp를 쓸 수 있게 되면 알려 준다.

        준비 전에 담긴 주소는 그대로 기다린다. 트레이로 시작해 로그인과 함께
        뜨는 경우 준비보다 주소가 먼저 들어올 수 있다.
        """
        self.ytdlp_path = path
        self._pump()

    def set_ignore_ssl_errors(self, ignore: bool):
        self.ignore_ssl_errors = bool(ignore)

    def set_wanted_check(self, predicate: Callable[[str], bool]):
        """아직 이 항목의 정보가 필요한지 물어볼 곳을 걸어 둔다.

        담아 둔 목록과 실제 대기열이 어긋날 여지를 없앤다. 취소를 빠뜨린 자리가
        하나라도 있으면 이미 받기 시작했거나 목록에서 지운 주소를 뒤늦게
        물어보게 되는데, 그건 아무도 보지 않을 답을 위해 회선을 쓰는 일이다.
        """
        self._is_wanted = predicate

    def request(self, url: str):
        """차례를 기다리는 항목 하나를 미리 물어볼 목록에 넣는다."""
        if self._shutting_down or not url:
            return
        if url in self._cache or url == self._current or url in self._pending:
            return
        self._pending.append(url)
        self._pump()

    def take(self, url: str) -> Optional[dict]:
        """받아 둔 정보를 넘기고 그 항목에 대한 미리 묻기를 끝낸다.

        받기 시작하는 자리에서 부른다. 담아 둔 것이 있으면 그대로 쓰고, 마침
        묻고 있었다면 그 질의를 죽인다. 어느 쪽이든 이 주소로는 더 묻지 않는다.
        """
        metadata = self._cache.pop(url, None)
        if metadata is None:
            self.cancel(url)
        return metadata

    def cancel(self, url: str):
        """이 주소는 이제 필요 없다고 알린다. 묻는 중이면 그만둔다."""
        if url in self._pending:
            self._pending.remove(url)
        self._cache.pop(url, None)
        if url == self._current and self._thread is not None:
            self._thread.stop()

    def stop_all(self):
        """앱을 끝낼 때 부른다. 담아 둔 것을 버리고 도는 질의를 거둔다."""
        self._shutting_down = True
        self._pending.clear()
        self._cache.clear()
        thread = self._thread
        self._thread = None
        self._current = None
        if thread is None:
            return
        thread.stop()
        thread.wait(QDeadlineTimer(self.STOP_WAIT_MS))

    def pending_count(self) -> int:
        """아직 답을 받지 못한 개수(줄 서 있는 것 + 묻는 중인 것)."""
        return len(self._pending) + (1 if self._current else 0)

    def _pump(self):
        """줄에서 하나를 꺼내 묻기 시작한다. 이미 묻는 중이면 아무것도 하지 않는다."""
        if self._shutting_down or self._thread is not None or not self.ytdlp_path:
            return
        while self._pending:
            url = self._pending.pop(0)
            if self._is_wanted is not None and not self._is_wanted(url):
                continue
            thread = MetadataThread(url, self.ytdlp_path, self.ignore_ssl_errors)
            thread.loaded.connect(self._on_loaded)
            thread.failed.connect(self._on_failed)
            thread.finished.connect(self._reap)
            self._current = url
            self._thread = thread
            self._retiring.append(thread)
            thread.start()
            return

    def _reap(self):
        """다 돈 질의 스레드를 거둔다.

        지워진 것부터 걸러 낸다. 빼먹으면 isFinished()가 RuntimeError를 내는데,
        슬롯 안의 예외라 PyQt6가 잡지 못해 앱이 그대로 죽는다(썸네일 스레드에서
        실제로 겪은 것과 같은 자리다).

        거두는 일을 loaded/failed 쪽에 두지 않는 것은, 그 신호가 run()의 마지막
        줄에서 나와 아직 스레드가 도는 중일 수 있어서다. QThread.finished는
        run()이 정말로 끝난 뒤에만 온다.
        """
        alive = []
        for thread in self._retiring:
            if sip.isdeleted(thread):
                continue
            if thread.isFinished():
                thread.deleteLater()
                continue
            alive.append(thread)
        self._retiring = alive

    def _finish(self, url: str):
        """묻던 항목 하나를 끝내고 다음으로 넘어간다."""
        if url != self._current:
            return
        self._thread = None
        self._current = None
        self._pump()

    def _on_loaded(self, url: str, metadata: dict):
        if self._shutting_down:
            return
        wanted = self._is_wanted is None or self._is_wanted(url)
        if wanted:
            self._cache[url] = metadata
        self._finish(url)
        if wanted:
            self.loaded.emit(url, metadata)

    def _on_failed(self, url: str, reason: str):
        """못 가져와도 알리지 않는다. 받을 때 DownloadThread가 다시 묻는다."""
        if self._shutting_down:
            return
        self._finish(url)
