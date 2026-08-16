"""tests/ 공통 준비물.

여기 있는 검사는 **QApplication을 띄우지 않는다.** 창을 만들고 눈으로 보는 일은
tools/ 쪽이 맡고, 이쪽은 값이 맞게 나오는지만 본다. 둘을 섞지 않는 이유는 실패의
뜻이 다르기 때문이다 — 이쪽이 빨개지면 계산이 틀린 것이고, tools/ 쪽이 이상하면
대개 화면 배치나 테마 문제다.

QObject와 시그널은 QApplication 없이도 동작한다(직접 연결이라 이벤트 루프가
필요 없다). 그래서 DownloadManager처럼 QObject를 물려받은 것도 여기서 돌릴 수
있다. QWidget을 만드는 순간부터는 안 되므로, 위젯이 필요한 검사는 tools/로 보낸다.
"""

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



class FakeDownloadThread(QObject):
    """DownloadThread 대역. yt-dlp를 띄우지 않고 신호만 흉내 낸다.

    진짜와 같은 시그널 두 개(progress, finished)를 들고 있어야 한다.
    DownloadManager가 만들자마자 여기에 connect하기 때문이다.

    start()는 일부러 아무것도 하지 않는다. 언제 '끝났다'고 할지는 검사가 정해야
    해서, finish()를 직접 불러 그 시점을 만든다.
    """

    progress = pyqtSignal(str, dict)
    finished = pyqtSignal(str, bool, str, dict)

    created = []

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.url = kwargs.get("url", "")
        self.started = False
        self.stopped = False
        self.waited = False
        FakeDownloadThread.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def wait(self, deadline=None):
        self.waited = True
        return True

    def emit_progress(self, payload):
        """진행률 한 줄이 올라온 것으로 친다."""
        self.progress.emit(self.url, payload)

    def finish(self, success=True, filepath="", metadata=None):
        """다운로드가 끝난 것으로 친다."""
        self.finished.emit(self.url, success, filepath, metadata or {})


class FakeConversionThread(QObject):
    """ConversionThread 대역. ffmpeg를 띄우지 않는다.

    finished의 인자 차례가 (성공, url, 새 경로)로 진짜와 같아야 한다. 여기가
    어긋나면 DownloadManager가 url 자리에 True를 받아 들고 조용히 헛돈다.
    """

    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)

    created = []

    def __init__(self, url, input_path, ffmpeg_path, **kwargs):
        super().__init__()
        self.url = url
        self.input_path = input_path
        self.ffmpeg_path = ffmpeg_path
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.waited = False
        FakeConversionThread.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def wait(self, deadline=None):
        self.waited = True
        return True

    def finish(self, success=True, new_filepath=""):
        """변환이 끝난 것으로 친다."""
        self.finished.emit(success, self.url, new_filepath)


@pytest.fixture
def fake_threads(monkeypatch):
    """DownloadManager가 만드는 스레드를 가짜로 바꿔 끼운다.

    **제품 코드는 한 줄도 고치지 않는다.** download_manager는 모듈 맨 위에서
    `from ... import DownloadThread`로 이름을 끌어오므로, 그 이름은
    src.download_manager 네임스페이스에 산다. 원본 모듈이 아니라 그쪽을 갈아
    끼우면 _start_download가 부르는 것이 가짜가 된다.

    이 방식을 고른 이유는 의존성 주입을 새로 넣지 않아도 되기 때문이다.
    생성자에 팩토리를 받게 고치면 제품 코드가 검사 때문에 바뀌고, 그 인자를
    실제로 쓰는 곳은 창 하나뿐이라 얻는 것이 없다.
    """
    import src.download_manager as dm

    FakeDownloadThread.created.clear()
    FakeConversionThread.created.clear()
    monkeypatch.setattr(dm, "DownloadThread", FakeDownloadThread)
    monkeypatch.setattr(dm, "ConversionThread", FakeConversionThread)
    return FakeDownloadThread, FakeConversionThread


class SignalRecorder:
    """시그널로 나온 값을 순서대로 담아 둔다."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args if len(args) != 1 else args[0])

    @property
    def last(self):
        return self.calls[-1] if self.calls else None

    def __len__(self):
        return len(self.calls)


@pytest.fixture
def recorder():
    return SignalRecorder


def make_config(**overrides):
    """DownloadManager에 넘길 최소 설정. 필요한 것만 덮어쓴다."""
    config = {
        "download_folder": "",
        "max_concurrent_downloads": 5,
        "conversion_format": "none",
        "preferred_codec": "original",
        "filename_parts": {"series": True, "episode": True},
        "filename_order": ["series", "episode"],
    }
    config.update(overrides)
    return config


@pytest.fixture
def config_factory():
    return make_config


class FakeResponse:
    """requests 응답 대역. GitHub 한도 판정에 필요한 두 가지만 들고 있다."""

    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


@pytest.fixture
def fake_response():
    return FakeResponse
