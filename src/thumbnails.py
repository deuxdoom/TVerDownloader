"""썸네일을 받아 오는 스레드 풀과 디스크·메모리 캐시. 위젯이 아니라 위젯에 그림을 대는 쪽이다.

**원본을 창 스레드에서 풀지 않는다.** TVer 표지는 1280x720 JPEG(평균 690KB)라 한 장 푸는 데
8ms, 1/8 크기로 읽어도 3.6ms가 든다(실측). 기록 카드 서른 장을 새로 그릴 때마다 창이 0.3초
멈춰서, 원본은 작업 스레드에서만 풀고 작은 사본(`small/`)과 메모리 캐시로 그린다.
"""
from __future__ import annotations
import hashlib
import os
import re
import threading
import urllib.request
from collections import OrderedDict, deque
from pathlib import Path
from typing import Optional

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QRectF, QSize, QBuffer, QByteArray
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QImage, QImageReader

THUMBNAIL_CACHE_DIR = Path("thumbnails")
SMALL_DIR_NAME = "small"
"""작은 사본을 두는 하위 폴더. 설정의 캐시 비우기가 `glob('**/*')`라 함께 지워진다."""

SMALL_SIZE = QSize(320, 180)
"""작은 사본의 크기. 가장 큰 자리(다운로드 카드 160x90)를 200% 배율에서 채우는 값이다."""

SMALL_QUALITY = 85
"""작은 사본의 JPEG 품질. 한 장 10~20KB라 푸는 데 0.3ms 안팎이다."""

MEMORY_LIMIT = 400
"""메모리에 들고 있는 완성본 수. 한 장 100KB 남짓이라 가득 차도 40MB를 넘지 않는다."""

SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

_running_thumb_threads: set = set()
_pending_thumbs: deque = deque()
_memory: "OrderedDict[tuple, QPixmap]" = OrderedDict()

MAX_CONCURRENT_THUMBS = 6
"""한 번에 띄우는 썸네일 스레드 수. **재 보고 정한 값이 아니라 근거가 남아 있지 않다.**

고칠 일이 생기면 지금 값을 근거로 삼지 말고, 첫 화면이 채워지는 시간을 새로 재서 정한다.
"""


def cache_key_for(tail: str, url: str) -> str:
    """캐시 파일 이름. 주소 끝 토막을 쓰되 파일 이름이 될 수 없으면 그림 주소의 해시로 짓는다.

    TVer 회차·시리즈 id는 그대로 이름이 되어 예전 캐시를 그대로 쓴다. 유튜브의 `watch?v=`처럼
    윈도우가 막는 글자가 든 끝 토막은 예전에 캐시를 아예 못 적어 목록을 그릴 때마다 받으러 갔다.
    """
    if tail and SAFE_KEY_RE.match(tail):
        return tail
    if not url:
        return ""
    return "u" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def original_path(key: str) -> Path:
    return THUMBNAIL_CACHE_DIR / f"{key}.jpg"


def small_path(key: str) -> Path:
    return THUMBNAIL_CACHE_DIR / SMALL_DIR_NAME / f"{key}.jpg"


def decode_small(data: Optional[bytes]) -> Optional[QImage]:
    """그림 바이트를 작은 사본 크기로 푼다. 그림이 아니면 None. 어느 스레드에서 불러도 된다."""
    if not data:
        return None
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    size = reader.size()
    if size.isValid() and (size.width() > SMALL_SIZE.width() or size.height() > SMALL_SIZE.height()):
        size.scale(SMALL_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        reader.setScaledSize(size)
    image = reader.read()
    return None if image.isNull() else image


def cached_thumbnail(path: Path) -> Optional[QImage]:
    """캐시에 둔 그림을 읽는다. 그림으로 읽히지 않으면 그 파일을 지우고 None을 준다.

    깨진 파일을 두면 '파일이 있다'는 이유로 다시 받지 않아 그 카드만 영영 빈칸으로
    남는다. 읽어 보고 지우면 이미 그런 파일을 들고 있는 사람도 다음에 켤 때 낫는다.
    """
    if not path.exists():
        return None
    image = QImage(str(path))
    if not image.isNull():
        return image
    try:
        path.unlink()
    except OSError:
        pass
    return None


def _write_atomic(path: Path, write) -> bool:
    """임시 이름에 쓰고 바꿔 단다. 같은 그림을 두 스레드가 동시에 적어도 반쪽 파일이 남지 않는다."""
    temp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not write(temp):
            raise OSError("write failed")
        os.replace(temp, path)
        return True
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def write_thumbnail_cache(path: Optional[Path], data: bytes) -> None:
    """받아 온 원본을 캐시에 적는다. 경로가 None이면 적을 자리가 없다는 뜻이지 실패가 아니다."""
    if path is None:
        return

    def write(temp: Path) -> bool:
        temp.write_bytes(data)
        return True

    _write_atomic(path, write)


def _save_small(key: str, image: QImage) -> None:
    _write_atomic(small_path(key), lambda temp: image.save(str(temp), "JPG", SMALL_QUALITY))


class ThumbnailDownloader(QThread):
    """그림 하나를 작은 사본까지 만들어 낸다. 디스크를 읽고 쓰는 일도 모두 여기서 한다.

    원본이 캐시에 있으면 받지 않고 그것을 푼다 - 작은 사본이 없던 4.3.0 전 캐시가 이 길로
    한 번씩 지나 작은 사본을 얻는다. 내보내는 것은 (주소, 받은 바이트, 작은 그림)이다.
    """
    loaded = pyqtSignal(object)

    def __init__(self, url: str, cache_key: str = ""):
        super().__init__(None)
        self.url = url
        self.cache_key = cache_key

    def run(self):
        data = image = None
        original = original_path(self.cache_key) if self.cache_key else None
        if original is not None and original.exists():
            try:
                data = original.read_bytes()
            except OSError:
                data = None
            image = decode_small(data)
            if image is None:
                data = None
                try:
                    original.unlink()
                except OSError:
                    pass
        if image is None:
            data = self._fetch()
            image = decode_small(data)
            if image is None:
                data = None
            elif original is not None:
                write_thumbnail_cache(original, data)
        if image is not None and self.cache_key:
            _save_small(self.cache_key, image)
        self.loaded.emit((self.url, data, image))

    def _fetch(self) -> Optional[bytes]:
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                return r.read()
        except Exception:
            return None


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


def _spawn_thumb_thread(url: str, on_loaded, cache_key: str = "") -> ThumbnailDownloader:
    thread = ThumbnailDownloader(url, cache_key)
    thread.loaded.connect(on_loaded)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(_get_coordinator().on_thread_finished)
    _running_thumb_threads.add(thread)
    thread.start()
    return thread


def _pump_thumb_queue():
    """자리가 나는 대로 대기 중인 요청을 시작한다."""
    while _pending_thumbs and len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        url, on_loaded, cache_key = _pending_thumbs.popleft()
        receiver = getattr(on_loaded, "__self__", None)
        if receiver is not None and sip.isdeleted(receiver):
            continue
        _spawn_thumb_thread(url, on_loaded, cache_key)


def start_thumbnail_download(url: str, on_loaded, cache_key: str = ""):
    """썸네일 요청을 넣는다. 동시 실행 수를 넘으면 대기열에 쌓인다.

    on_loaded는 QObject의 바운드 메서드여야 한다 - 람다는 수신자가 사라져도 연결이
    끊기지 않아 삭제된 위젯을 건드리며 죽는다. 주소가 비면 스레드를 쓰지 않는다.
    """
    if not url or not isinstance(url, str):
        return None
    if len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        return _spawn_thumb_thread(url, on_loaded, cache_key)
    _pending_thumbs.append((url, on_loaded, cache_key))
    return None


def discard_thumbnail_requests(receiver) -> int:
    """이 카드가 걸어 둔 '아직 시작 전' 썸네일 요청을 대기열에서 뺀다.

    _pump_thumb_queue의 걸러 내기는 deleteLater가 처리된 뒤에야 참이 되어, 목록을
    새로 그리는 그 순간에는 늦다. 되돌려주는 수는 검사용이다.
    """
    if receiver is None:
        return 0
    remaining = [entry for entry in _pending_thumbs
                 if getattr(entry[1], "__self__", None) is not receiver]
    dropped = len(_pending_thumbs) - len(remaining)
    if dropped:
        _pending_thumbs.clear()
        _pending_thumbs.extend(remaining)
    return dropped


def _memory_key(key: str, width: int, height: int, dpr: float, radius: int) -> tuple:
    return (key, width, height, round((dpr or 1.0) * 100), radius)


def remember_thumbnail(key: str, image: QImage, width: int, height: int,
                       dpr: float = 1.0, radius: int = 4) -> QPixmap:
    """작은 그림으로 완성본을 만들어 메모리에 담고 돌려준다. 창 스레드에서만 부른다."""
    pixmap = rounded_thumbnail(QPixmap.fromImage(image), width, height, dpr, radius)
    if key:
        memory_key = _memory_key(key, width, height, dpr, radius)
        _memory[memory_key] = pixmap
        _memory.move_to_end(memory_key)
        while len(_memory) > MEMORY_LIMIT:
            _memory.popitem(last=False)
    return pixmap


def lookup_thumbnail(key: str, width: int, height: int,
                     dpr: float = 1.0, radius: int = 4) -> Optional[QPixmap]:
    """메모리 → 작은 사본 순으로 찾는다. 없으면 None이고 부르는 쪽이 받으러 보낸다.

    원본만 있는 경우도 None이다 - 그것을 푸는 일은 작업 스레드의 몫이다.
    """
    if not key:
        return None
    memory_key = _memory_key(key, width, height, dpr, radius)
    pixmap = _memory.get(memory_key)
    if pixmap is not None:
        _memory.move_to_end(memory_key)
        return pixmap
    image = cached_thumbnail(small_path(key))
    if image is None:
        return None
    return remember_thumbnail(key, image, width, height, dpr, radius)


def forget_memory_cache() -> None:
    """메모리에 든 완성본을 버린다. 설정에서 캐시를 비운 뒤 옛 그림이 남지 않게 한다."""
    _memory.clear()


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
