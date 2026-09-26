"""썸네일을 받아 오는 스레드 풀과 디스크·메모리 캐시. 위젯이 아니라 위젯에 그림을 대는 쪽이다.

**원본을 창 스레드에서 풀지 않는다.** TVer 표지는 1280x720 JPEG(평균 690KB)라 한 장 푸는 데
8ms, 1/8 크기로 읽어도 3.6ms가 든다(실측). 작업 스레드가 목록용 작은 사본(`cards/`)을 만들고
창은 그것과 메모리 캐시로 그린다. 원본(`originals/`)은 저장·확대를 하는 다운로드 카드만 남긴다.
"""
from __future__ import annotations
import hashlib
import os
import re
import threading
import time
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QRectF, QSize, QBuffer, QByteArray
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QImage, QImageReader

THUMBNAIL_CACHE_DIR = Path("thumbnails")
SMALL_DIR_NAME = "cards"
"""목록용 작은 사본을 두는 하위 폴더. 설정의 캐시 비우기가 `glob('**/*')`라 함께 지워진다."""

ORIGINAL_DIR_NAME = "originals"
"""원본을 두는 하위 폴더. 원본을 달라고 한 요청(다운로드 카드)만 여기에 적는다."""

LEGACY_SMALL_DIR_NAME = "small"
"""4.4.0 전의 작은 사본 폴더. 원본은 캐시 폴더 바로 아래에 있었다. 둘 다 한 번 비운다.

그때는 yt-dlp의 대표 그림을 받았는데 テレビ朝日 회차는 그것이 방송사 로고였고, 캐시 이름이
회차 id뿐이라 한 번 들어간 로고가 바뀌지 않았다. 어느 것이 로고인지 가릴 수 없어 통째로 버린다.
"""

ORIGINAL_KEEP_DAYS = 30
"""원본을 남겨 두는 기간. 목록 카드는 작은 사본만 쓰므로 원본은 받은 직후에만 쓸모가 있다."""

FAILED_RETRY_S = 600
"""받지 못한 주소를 다시 받으러 가지 않는 시간. 기록을 새로 그릴 때마다 같은 403을 받지 않게 한다."""

SMALL_SIZE = QSize(320, 180)
"""작은 사본의 크기. 가장 큰 자리(다운로드 카드 160x90)를 200% 배율에서 채우는 값이다."""

SMALL_QUALITY = 85
"""작은 사본의 JPEG 품질. 한 장 10~20KB라 푸는 데 0.3ms 안팎이다."""

MEMORY_LIMIT = 400
"""메모리에 들고 있는 완성본 수. 한 장 100KB 남짓이라 가득 차도 40MB를 넘지 않는다."""

SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

MAX_CONCURRENT_THUMBS = 6
"""한 번에 띄우는 썸네일 스레드 수. **재 보고 정한 값이 아니라 근거가 남아 있지 않다.**

고칠 일이 생기면 지금 값을 근거로 삼지 말고, 첫 화면이 채워지는 시간을 새로 재서 정한다.
"""


@dataclass
class _Job:
    """받을 그림 하나. 같은 것을 여러 카드가 기다려도 한 번만 받는다."""
    url: str
    key: str
    want_original: bool
    receivers: List[Callable] = field(default_factory=list)


_jobs: "Dict[tuple, _Job]" = {}
_pending_thumbs: deque = deque()
"""아직 시작하지 않은 요청의 id. 요청 내용과 기다리는 쪽은 _jobs에 있다."""
_running_thumb_threads: set = set()
_thread_jobs: "Dict[ThumbnailDownloader, tuple]" = {}
_failed: Dict[str, float] = {}
_memory: "OrderedDict[tuple, QPixmap]" = OrderedDict()


def cache_key_for(tail: str, url: str) -> str:
    """캐시 파일 이름. 주소 끝 토막을 쓰되 파일 이름이 될 수 없으면 그림 주소의 해시로 짓는다.

    TVer 회차·시리즈 id는 그대로 이름이 된다. 유튜브의 `watch?v=`처럼 윈도우가 막는 글자가 든
    끝 토막은 예전에 캐시를 아예 못 적어 목록을 그릴 때마다 받으러 갔다.
    """
    if tail and SAFE_KEY_RE.match(tail):
        return tail
    if not url:
        return ""
    return "u" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def original_path(key: str) -> Path:
    return THUMBNAIL_CACHE_DIR / ORIGINAL_DIR_NAME / f"{key}.jpg"


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

    깨진 파일을 두면 '파일이 있다'는 이유로 다시 받지 않아 그 카드만 영영 빈칸으로 남는다.
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

    원본이 캐시에 있으면 받지 않고 그것을 푼다. 받은 원본은 want_original일 때만 적는다.
    내보내는 것은 (요청 id, (주소, 받은 바이트, 작은 그림))이다.
    """
    loaded = pyqtSignal(object)

    def __init__(self, url: str, cache_key: str = "", want_original: bool = False,
                 job_id: Optional[tuple] = None):
        super().__init__(None)
        self.url = url
        self.cache_key = cache_key
        self.want_original = want_original
        self.job_id = job_id

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
            elif self.want_original:
                write_thumbnail_cache(original, data)
        if image is not None and self.cache_key:
            _save_small(self.cache_key, image)
        self.loaded.emit((self.job_id, (self.url, data, image)))

    def _fetch(self) -> Optional[bytes]:
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                return r.read()
        except Exception:
            return None


def _alive(callback: Callable) -> bool:
    """받는 쪽이 아직 살아 있는가. Qt 객체가 아니면 sip.isdeleted가 TypeError를 내므로 살아 있다고 본다."""
    receiver = getattr(callback, "__self__", None)
    return not isinstance(receiver, sip.simplewrapper) or not sip.isdeleted(receiver)


class _ThumbCoordinator(QObject):
    """작업 스레드의 결과와 종료를 창 스레드에서 받는다.

    메인 스레드에 사는 QObject를 수신자로 두어야 Qt가 큐 연결로 바꿔, 기다리는 카드에 결과를
    넘기는 일과 새 QThread를 만드는 일이 모두 창 스레드에서 일어난다.
    """

    def on_loaded(self, payload):
        """기다리던 쪽 모두에게 결과를 넘긴다. 그림이 아니었으면 한동안 다시 받지 않는다."""
        job_id, result = payload
        job = _jobs.pop(job_id, None)
        url, _data, image = result
        if image is None:
            _failed[url] = time.monotonic()
        else:
            _failed.pop(url, None)
        if job is None:
            return
        for callback in job.receivers:
            if _alive(callback):
                callback(result)

    def on_thread_finished(self):
        """끝난 스레드를 걷어내고 다음 요청을 띄운다. 이미 지워진 스레드를 먼저 본다.

        finished에 걸린 deleteLater와 순서 보장이 없어 C++ 객체가 먼저 파괴될 수 있다.
        isFinished()가 내는 RuntimeError는 슬롯 안의 예외라 PyQt6가 못 잡고 앱이 죽는다.
        결과를 내지 못하고 끝난 요청은 여기서 지워야 같은 그림을 다시 요청할 수 있다.
        """
        for thread in list(_running_thumb_threads):
            if sip.isdeleted(thread) or thread.isFinished():
                _running_thumb_threads.discard(thread)
                job_id, job = _thread_jobs.pop(thread, (None, None))
                if job is not None and _jobs.get(job_id) is job:
                    del _jobs[job_id]
        _pump_thumb_queue()


_coordinator: "Optional[_ThumbCoordinator]" = None


def _get_coordinator() -> "_ThumbCoordinator":
    global _coordinator
    if _coordinator is None:
        _coordinator = _ThumbCoordinator()
    return _coordinator


def _spawn_thumb_thread(job_id: tuple, job: _Job) -> ThumbnailDownloader:
    coordinator = _get_coordinator()
    thread = ThumbnailDownloader(job.url, job.key, job.want_original, job_id)
    thread.loaded.connect(coordinator.on_loaded)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(coordinator.on_thread_finished)
    _running_thumb_threads.add(thread)
    _thread_jobs[thread] = (job_id, job)
    thread.start()
    return thread


def _pump_thumb_queue():
    """자리가 나는 대로 대기 중인 요청을 시작한다. 기다리는 쪽이 모두 사라진 요청은 버린다."""
    while _pending_thumbs and len(_running_thumb_threads) < MAX_CONCURRENT_THUMBS:
        job_id = _pending_thumbs.popleft()
        job = _jobs.get(job_id)
        if job is None:
            continue
        job.receivers = [callback for callback in job.receivers if _alive(callback)]
        if not job.receivers:
            del _jobs[job_id]
            continue
        _spawn_thumb_thread(job_id, job)


def start_thumbnail_download(url: str, on_loaded, cache_key: str = "",
                             want_original: bool = False) -> None:
    """그림 하나를 요청한다. 같은 것을 받는 중이면 거기에 얹고, 자리가 없으면 줄을 선다.

    on_loaded는 QObject의 바운드 메서드여야 한다 - 받는 쪽이 헐렸는지 그것으로 가린다.
    주소가 비었거나 방금 받지 못한 주소면 아무것도 하지 않는다.
    """
    if not url or not isinstance(url, str):
        return
    failed_at = _failed.get(url)
    if failed_at is not None and time.monotonic() - failed_at < FAILED_RETRY_S:
        return
    job_id = (url, cache_key, bool(want_original))
    job = _jobs.get(job_id)
    if job is None:
        job = _jobs[job_id] = _Job(url, cache_key, bool(want_original))
        _pending_thumbs.append(job_id)
    if on_loaded not in job.receivers:
        job.receivers.append(on_loaded)
    _pump_thumb_queue()


def discard_thumbnail_requests(receiver) -> int:
    """이 카드가 걸어 둔 요청에서 빠진다. 기다리는 쪽이 없어진 '아직 시작 전' 요청은 버린다.

    목록을 새로 그리는 그 순간에 부른다 - deleteLater가 처리되기 전이라 헐렸는지로는 가릴 수
    없다. 받는 중인 것은 그대로 두어 캐시는 채운다. 되돌려주는 수(빠진 요청 수)는 검사용이다.
    """
    if receiver is None:
        return 0
    dropped = 0
    for job in _jobs.values():
        kept = [callback for callback in job.receivers
                if getattr(callback, "__self__", None) is not receiver]
        dropped += len(job.receivers) - len(kept)
        job.receivers = kept
    orphaned = [job_id for job_id in _pending_thumbs
                if job_id not in _jobs or not _jobs[job_id].receivers]
    if orphaned:
        for job_id in orphaned:
            _jobs.pop(job_id, None)
        remaining = [job_id for job_id in _pending_thumbs if job_id in _jobs]
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
    """메모리에 든 완성본과 실패 기록을 버린다. 설정에서 캐시를 비운 뒤 옛 그림이 남지 않게 한다."""
    _memory.clear()
    _failed.clear()


def prune_cache(now: Optional[float] = None) -> int:
    """4.4.0 전 배치의 파일과 기한이 지난 원본을 지우고 지운 개수를 돌려준다. 실패는 삼킨다."""
    root = THUMBNAIL_CACHE_DIR
    legacy = root / LEGACY_SMALL_DIR_NAME
    cutoff = (time.time() if now is None else now) - ORIGINAL_KEEP_DAYS * 86400
    targets: List[Path] = []
    for folder, expired_only in ((root, False), (legacy, False), (root / ORIGINAL_DIR_NAME, True)):
        try:
            for path in folder.iterdir():
                if path.is_file() and (not expired_only or path.stat().st_mtime < cutoff):
                    targets.append(path)
        except OSError:
            continue
    removed = 0
    for path in targets:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    try:
        legacy.rmdir()
    except OSError:
        pass
    return removed


def start_cache_maintenance() -> None:
    """prune_cache를 따로 돌린다. 옛 캐시가 수백 장이라 창을 짓는 동안 막지 않게 한다."""
    threading.Thread(target=prune_cache, name="thumbnail-prune", daemon=True).start()


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
