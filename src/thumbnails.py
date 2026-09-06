"""썸네일을 받아 오는 스레드 풀과 디스크 캐시. 위젯이 아니라 위젯에 그림을 대는 쪽이다.

동시 실행 수와 대기열이 모듈 전역 하나뿐이라, 카드 위젯과 같은 파일에 두면 그 전역이
위젯 정의 사이에 흩어진다. 쓰는 곳은 세 카드 위젯과 시리즈 선택 창·설정 창이다.
"""
from __future__ import annotations
import urllib.request
from collections import deque
from pathlib import Path
from typing import Optional

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath

THUMBNAIL_CACHE_DIR = Path("thumbnails")


_running_thumb_threads: set = set()
_pending_thumbs: deque = deque()

MAX_CONCURRENT_THUMBS = 6
"""한 번에 띄우는 썸네일 스레드 수. **재 보고 정한 값이 아니라 근거가 남아 있지 않다.**

고칠 일이 생기면 지금 값을 근거로 삼지 말고, 첫 화면이 채워지는 시간을 새로 재서 정한다.
"""


class ThumbnailDownloader(QThread):
    loaded = pyqtSignal(object)

    def __init__(self, url: str):
        super().__init__(None)
        self.url = url

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                data = r.read()
        except Exception:
            data = None
        self.loaded.emit((self.url, data))


class _ThumbCoordinator(QObject):
    """썸네일 스레드의 종료를 메인 스레드에서 받아 다음 요청을 시작한다.

    QThread.finished는 워커 스레드에서 난다. 메인 스레드에 사는 QObject를 수신자로
    두어야 Qt가 큐 연결로 바꿔, 워커 스레드에서 새 QThread를 만드는 일이 없다.
    """

    def on_thread_finished(self):
        """이미 지워진 스레드를 먼저 걷어낸다.

        finished에 걸린 deleteLater와 순서 보장이 없어 C++ 객체가 먼저 파괴될 수 있다.
        isFinished()가 내는 RuntimeError는 슬롯 안의 예외라 PyQt6가 못 잡고 앱이 죽는다.
        """
        for thread in list(_running_thumb_threads):
            if sip.isdeleted(thread) or thread.isFinished():
                _running_thumb_threads.discard(thread)
        _pump_thumb_queue()


_coordinator: "Optional[_ThumbCoordinator]" = None


def _get_coordinator() -> "_ThumbCoordinator":
    global _coordinator
    if _coordinator is None:
        _coordinator = _ThumbCoordinator()
    return _coordinator


def _spawn_thumb_thread(url: str, on_loaded) -> ThumbnailDownloader:
    thread = ThumbnailDownloader(url)
    thread.loaded.connect(on_loaded)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(_get_coordinator().on_thread_finished)
    _running_thumb_threads.add(thread)
    thread.start()
    return thread


def _pump_thumb_queue():
    """자리가 나는 대로 대기 중인 요청을 시작한다."""
    while _pending_thumbs and len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        url, on_loaded = _pending_thumbs.popleft()
        receiver = getattr(on_loaded, "__self__", None)
        if receiver is not None and sip.isdeleted(receiver):
            continue
        _spawn_thumb_thread(url, on_loaded)


def start_thumbnail_download(url: str, on_loaded):
    """썸네일 요청을 넣는다. 동시 실행 수를 넘으면 대기열에 쌓인다.

    on_loaded는 QObject의 바운드 메서드여야 한다 - 람다는 수신자가 사라져도 연결이
    끊기지 않아 삭제된 위젯을 건드리며 죽는다. 주소가 비면 스레드를 쓰지 않는다.
    """
    if not url or not isinstance(url, str):
        return None
    if len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        return _spawn_thumb_thread(url, on_loaded)
    _pending_thumbs.append((url, on_loaded))
    return None


def cached_thumbnail(path: Path) -> Optional[QPixmap]:
    """캐시에 둔 그림을 읽는다. 그림으로 읽히지 않으면 그 파일을 지우고 None을 준다.

    깨진 파일을 두면 '파일이 있다'는 이유로 다시 받지 않아 그 카드만 영영 빈칸으로
    남는다. 읽어 보고 지우면 이미 그런 파일을 들고 있는 사람도 다음에 켤 때 낫는다.
    """
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        return pixmap
    try:
        path.unlink()
    except OSError:
        pass
    return None


def write_thumbnail_cache(path: Optional[Path], data: bytes) -> None:
    """받아 온 그림을 캐시에 적는다. **폴더를 만드는 일도 여기서만 한다.**

    카드가 생길 때마다 mkdir을 부르던 것을 이 자리로 모았다(실측: 100회 9.8ms).
    캐시를 두지 않는 카드는 경로가 None으로 오는데, 적을 자리가 없다는 뜻이지 실패가 아니다.
    """
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        pass


def discard_thumbnail_requests(receiver) -> int:
    """이 카드가 걸어 둔 '아직 시작 전' 썸네일 요청을 대기열에서 뺀다.

    _pump_thumb_queue의 걸러 내기는 deleteLater가 처리된 뒤에야 참이 되어, 목록을
    새로 그리는 그 순간에는 늦다. 되돌려주는 수는 검사용이다.
    """
    if receiver is None:
        return 0
    remaining = [pair for pair in _pending_thumbs
                 if getattr(pair[1], "__self__", None) is not receiver]
    dropped = len(_pending_thumbs) - len(remaining)
    if dropped:
        _pending_thumbs.clear()
        _pending_thumbs.extend(remaining)
    return dropped


def rounded_thumbnail(pixmap: QPixmap, width: int, height: int,
                      dpr: float = 1.0, radius: int = 4) -> QPixmap:
    """가운데를 잘라 지정 크기를 꽉 채우고 모서리를 둥글린다. KeepAspectRatio는 위아래가 남는다."""
    dpr = dpr or 1.0
    dev_w, dev_h = round(width * dpr), round(height * dpr)
    scaled = pixmap.scaled(dev_w, dev_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(dev_w, dev_h)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    source = QRectF((scaled.width() - dev_w) / 2, (scaled.height() - dev_h) / 2, dev_w, dev_h)
    painter.drawPixmap(QRectF(0, 0, width, height), scaled, source)
    painter.end()
    return out
