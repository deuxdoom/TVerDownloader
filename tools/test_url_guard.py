import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMainWindow, QMessageBox

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
import src.message as message
from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.utils import is_media_url, load_config

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []

EP = "https://tver.jp/episodes/ep6hzy79h"
SR = "https://tver.jp/series/sryhqsa8t0"
YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle():
    for _ in range(4):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


def teardown(*windows):
    """app이 살아 있는 동안 창을 정리한다.

    파이썬이 끝난 뒤 Qt 위젯이 파괴되면 이벤트 루프가 없어 이따금 segfault로 끝난다.
    무해한 잔여 현상이지만 종료 코드가 139가 되어 검증 결과를 가린다.
    """
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


print("=== 1. 주소로 받아 주는 것 ===")
ACCEPT = [
    EP, SR, YT,
    "http://tver.jp/episodes/ep1",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.nicovideo.jp/watch/sm9",
    "https://tver.jp",
    "https://vimeo.com/123456789?foo=bar#t=10",
    "HTTPS://TVER.JP/EPISODES/EP1",
    "https://tver.jp:443/episodes/ep1",
]
for text in ACCEPT:
    report(f"통과: {text}", is_media_url(text) is True)

print()
print("=== 2. 거르는 것 ===")
REJECT = [
    ("빈 값", ""),
    ("공백만", "   "),
    ("문장", "이 영상 좀 받아줘"),
    ("낱말", "테스트"),
    ("일본어 제목", "テスト番組 第12話"),
    ("파일 경로", r"C:\Users\Eric\video.mp4"),
    ("파일 이름", "memo.txt"),
    ("숫자", "3.14"),
    ("체계 없는 주소", "tver.jp/episodes/ep1"),
    ("www만", "www.youtube.com/watch?v=1"),
    ("주소가 섞인 문장", f"이거 받아줘 {EP} 부탁"),
    ("공백이 낀 주소", "https://tver.jp/epi sodes/ep1"),
    ("호스트에 점이 없다", "https://localhost/episodes/ep1"),
    ("다른 체계", "ftp://tver.jp/episodes/ep1"),
    ("검색어처럼 보이는 것", "ytsearch:고양이"),
]
for label, text in REJECT:
    report(f"거름: {label}", is_media_url(text) is False, f"{text!r}")

print()
print("=== 3. 입력창에서 다운로드를 눌렀을 때 ===")


class Host(QMainWindow):
    """MainWindow에서 입력 처리 부분만 떼어 붙인 시험대."""

    BAD_URL_PREVIEW = T.MainWindow.BAD_URL_PREVIEW
    BAD_URL_ELIDE = T.MainWindow.BAD_URL_ELIDE

    def __init__(self, config):
        super().__init__()
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = config
        self.logs = []
        self.processed = []

    def append_log(self, text):
        self.logs.append(text)

    def _process_url(self, url):
        self.processed.append(url)

    _elide = staticmethod(T.MainWindow._elide)
    _notify_bad_url = T.MainWindow._notify_bad_url
    process_input_url = T.MainWindow.process_input_url


shown = []
real_notify = message.notify


def fake_notify(parent, title, text, **kwargs):
    shown.append((title, text, kwargs))


T.notify = fake_notify

config = load_config()
config["theme"] = "light"
host = Host(config)
host.show()
settle()

host.ui.url_input.setText(EP)
host.process_input_url()
report("주소는 그대로 넘어간다", host.processed == [EP], f"{host.processed}")
report("넘어간 뒤에는 입력칸을 비운다", host.ui.url_input.text() == "")
report("알림을 띄우지 않는다", shown == [])

host.processed.clear()
host.ui.url_input.setText("이 영상 좀 받아줘")
host.process_input_url()
report("주소가 아니면 다운로드를 시도하지 않는다", host.processed == [], f"{host.processed}")
report("알림을 한 번 띄운다", len(shown) == 1, f"{shown}")
report("입력칸을 지우지 않는다", host.ui.url_input.text() == "이 영상 좀 받아줘",
       f"{host.ui.url_input.text()!r}")
report("무엇을 넣었는지 알림에 보여 준다", "이 영상 좀 받아줘" in shown[0][1], f"{shown[0][1]!r}")
report("어떻게 고칠지도 알려 준다", "https://" in shown[0][1])

shown.clear()
host.processed.clear()
host.ui.url_input.setText("   ")
host.process_input_url()
report("빈 칸은 조용히 넘어간다", host.processed == [] and shown == [])

print()
print("=== 4. 긴 글은 줄여서 보여 준다 ===")
long_text = "가" * 200
shown.clear()
host.ui.url_input.setText(long_text)
host.process_input_url()
body_lines = shown[0][1].splitlines()
longest = max(len(line) for line in body_lines)
report("한 줄이 지나치게 길어지지 않는다", longest <= host.BAD_URL_ELIDE,
       f"가장 긴 줄={longest}자")
report("줄였다는 표시가 붙는다", any("…" in line for line in body_lines))

shown.clear()
host._notify_bad_url("t", "lead", [f"줄{i}" for i in range(9)])
body = shown[0][1]
report("다섯 줄까지만 보여 준다", body.count("줄") == host.BAD_URL_PREVIEW,
       f"{body!r}")
report("나머지는 개수로 줄인다", "외 4개" in body, f"{body!r}")

print()
print("=== 5. 다중 추가에서 걸러 낸다 ===")


class BulkHost(Host):
    """다중 추가 창이 돌려준 목록을 처리하는 부분만 흉내 낸다."""

    def __init__(self, config, lines):
        super().__init__(config)
        self._lines = lines
        self.env_ready = True
        self.added = []
        self.parsed = []
        self.series_parser = self
        self._bulk_dialog = None

    def _ensure_download_folder(self):
        return True

    def _request_add_task(self, url):
        self.added.append(url)
        return True

    def parse(self, context, urls):
        self.parsed.append((context, list(urls)))

    open_bulk_add = T.MainWindow.open_bulk_add


class FakeDialog:
    """exec()가 곧바로 수락하고 준비된 목록을 돌려주는 다중 추가 창."""

    def __init__(self, parent=None, initial_urls=None):
        self.urls = list(FakeDialog.lines)

    def exec(self):
        return 1

    def get_urls(self):
        return self.urls


real_dialog = T.BulkAddDialog
T.BulkAddDialog = FakeDialog

FakeDialog.lines = [EP, "이건 주소가 아님", SR, "memo.txt", YT]
shown.clear()
bulk = BulkHost(config, FakeDialog.lines)
bulk.open_bulk_add()
report("주소인 줄만 대기열로 간다", bulk.added == [EP, YT], f"{bulk.added}")
report("시리즈도 주소인 것만", bulk.parsed == [("bulk", [SR])], f"{bulk.parsed}")
report("걸러 낸 줄을 알린다", len(shown) == 1, f"{shown}")
report("걸러 낸 줄이 알림에 보인다",
       "이건 주소가 아님" in shown[0][1] and "memo.txt" in shown[0][1], f"{shown[0][1]!r}")
report("로그에도 남긴다", any("2줄" in line for line in bulk.logs), f"{bulk.logs}")

FakeDialog.lines = [EP, SR]
shown.clear()
clean = BulkHost(config, FakeDialog.lines)
clean.open_bulk_add()
report("모두 주소면 알리지 않는다", shown == [] and clean.added == [EP], f"{shown}")

T.BulkAddDialog = real_dialog
T.notify = real_notify

print()
print("=== 6. 알림 창 렌더 ===")
for theme in ("light", "dark"):
    app.setStyleSheet(build_qss(theme))
    measured = {}

    def probe():
        box = app.activeModalWidget()
        settle()
        buttons = box.findChild(QDialogButtonBox)
        measured["buttons"] = [b.text() for b in buttons.buttons()]
        box.grab().save(f"{OUT}/notify_bad_url_{theme}.png")
        box.accept()

    QTimer.singleShot(120, probe)
    real_notify(None, "주소를 확인해주세요",
                "다운로드할 수 있는 주소가 아닙니다.\n\n이 영상 좀 받아줘\n\n"
                "http:// 또는 https:// 로 시작하는\n영상 페이지 주소를 넣어주세요.",
                icon_name="info", color_key="warn", theme=theme)
    report(f"[{theme}] 단추가 확인 하나뿐", measured.get("buttons") == ["확인"],
           f"{measured.get('buttons')}")

report("notify가 QMessageBox 정적 함수를 쓰지 않는다",
       "information" not in message.notify.__code__.co_names,
       f"{message.notify.__code__.co_names}")
report("확인 창과 같은 상자를 쓴다", QMessageBox in message._ConfirmBox.__mro__)

teardown(host, bulk, clean)

print()
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
