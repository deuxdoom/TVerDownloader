import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QListWidgetItem

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import src.series_parser as sp
from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.widgets import DownloadItemWidget
import TVerDownloader as T

app.setStyleSheet(build_qss("light"))
results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


print("=== 1. 분석 대기열 우선순위 ===")


class FakeThread:
    """스레드를 띄우지 않고 대기열 순서만 본다."""
    started = []

    def __init__(self, url, path, keywords, title_only=False):
        self.url = url
        self.title_only = title_only

    class _Sig:
        def connect(self, *a):
            pass

    log = _Sig()
    finished = _Sig()

    def start(self):
        FakeThread.started.append(self.url)


real = sp.SeriesParseThread
sp.SeriesParseThread = FakeThread
try:
    parser = sp.SeriesParser(ytdlp_path="yt-dlp.exe", config={})
    parser.parse("fav-check", ["fav1", "fav2", "fav3", "fav4"])
    order_before = [c for c, _ in parser._queue]
    parser.parse("single", ["USER-A"])
    parser.parse("single", ["USER-B"])
    order_after = [(c, u) for c, u in parser._queue]

    ok = order_after[0] == ("single", "USER-A") and order_after[1] == ("single", "USER-B")
    report("사용자 요청이 즐겨찾기 확인 앞으로 끼어든다", ok,
           f"진행중={FakeThread.started} 대기열={order_after}")

    ok = [c for c, _ in order_after].count("fav-check") == 3
    report("끼어들어도 즐겨찾기 항목은 사라지지 않는다", ok,
           f"fav-check 잔여 {[u for c, u in order_after if c == 'fav-check']}")

    FakeThread.started.clear()
    idle = sp.SeriesParser(ytdlp_path="yt-dlp.exe", config={})
    idle.parse("fav-check", ["only"])
    report("비어 있을 때 즉시 시작", FakeThread.started == ["only"],
           f"started={FakeThread.started}")
finally:
    sp.SeriesParseThread = real


print()
print("=== 2. 즐겨찾기 신규 개수에 따른 분기 ===")


class FakeStore:
    def __init__(self, known=()):
        self.known = set(known)

    def exists(self, url):
        return url in self.known

    def touch_last_check(self, *a, **kw):
        pass


class Host(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = {"theme": "light"}
        self.history_store = FakeStore()
        self.fav_store = FakeStore()
        self.logs = []
        self.added = []
        self.dialog_calls = []

    def append_log(self, text):
        self.logs.append(text)

    def refresh_fav_list(self):
        pass

    def _request_add_task(self, url):
        self.added.append(url)
        return True

    def _add_from_selection(self, episode_info, label):
        self.dialog_calls.append((len(episode_info), label))

    _on_series_parsed = T.MainWindow._on_series_parsed


def eps(n, start=0):
    return [{"url": f"https://tver.jp/episodes/e{i}", "title": f"ep{i}",
             "thumbnail_url": ""} for i in range(start, start + n)]


for count, expect_dialog in [(1, False), (2, False), (3, True), (12, True), (70, True)]:
    h = Host()
    h._on_series_parsed("fav-check", "https://tver.jp/series/sr1", "아메토크", eps(count))
    used_dialog = bool(h.dialog_calls)
    ok = used_dialog == expect_dialog and (len(h.added) == count if not expect_dialog else not h.added)
    report(f"신규 {count}개 -> {'선택창' if expect_dialog else '바로 추가'}", ok,
           f"바로추가={len(h.added)}개, 선택창={h.dialog_calls}")
    h.close()

h = Host()
h.history_store = FakeStore(known=[f"https://tver.jp/episodes/e{i}" for i in range(8)])
h._on_series_parsed("fav-check", "https://tver.jp/series/sr1", "아메토크", eps(10))
ok = not h.dialog_calls and len(h.added) == 2
report("이미 받은 8개를 뺀 신규 2개 -> 바로 추가", ok,
       f"바로추가={h.added}, 선택창={h.dialog_calls}")
h.close()

h = Host()
h.history_store = FakeStore(known=[f"https://tver.jp/episodes/e{i}" for i in range(10)])
h._on_series_parsed("fav-check", "https://tver.jp/series/sr1", "아메토크", eps(10))
ok = not h.dialog_calls and not h.added
report("신규 0개 -> 아무것도 안 함", ok, f"로그={h.logs}")
h.close()

h = Host()
h._on_series_parsed("single", "https://tver.jp/series/sr1", "아메토크", eps(30))
ok = h.dialog_calls and h.dialog_calls[0][0] == 30
report("시리즈 URL 직접 입력은 개수 상관없이 선택창", bool(ok), f"{h.dialog_calls}")
h.close()


print()
print("=== 3. 선택 항목 취소 / 대기열 제거 ===")


class FakeManager:
    def __init__(self):
        self._active_threads = {}
        self._active_conversions = {}
        self._task_queue = []
        self.stopped = []

    def stop_task(self, url):
        self.stopped.append(url)

    def remove_task_from_queue(self, url):
        if url in self._task_queue:
            self._task_queue.remove(url)
            return True
        return False


class CancelHost(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = {"theme": "light"}
        self.download_manager = FakeManager()
        self.logs = []
        self.ui.download_list.itemSelectionChanged.connect(self._sync_cancel_button)
        self.ui.cancel_selected_button.clicked.connect(self._cancel_selected_downloads)

    def append_log(self, text):
        self.logs.append(text)

    _cancel_selected_downloads = T.MainWindow._cancel_selected_downloads
    _sync_cancel_button = T.MainWindow._sync_cancel_button
    _remove_download_row = T.MainWindow._remove_download_row


host = CancelHost()
host.resize(1100, 700)
host.show()
app.processEvents()

states = [("active1", "active"), ("queued1", "queued"), ("queued2", "queued"),
          ("done1", "done"), ("active2", "active"), ("queued3", "queued")]
for url, state in states:
    it = QListWidgetItem()
    w = DownloadItemWidget(url, "light")
    it.setSizeHint(w.sizeHint())
    host.ui.download_list.addItem(it)
    host.ui.download_list.setItemWidget(it, w)
    if state == "active":
        host.download_manager._active_threads[url] = object()
    elif state == "queued":
        host.download_manager._task_queue.append(url)
app.processEvents()

report("선택 없으면 버튼 비활성", not host.ui.cancel_selected_button.isEnabled())

for i in range(host.ui.download_list.count()):
    host.ui.download_list.item(i).setSelected(True)
app.processEvents()
report("선택하면 버튼 활성", host.ui.cancel_selected_button.isEnabled())

before = host.ui.download_list.count()
host._cancel_selected_downloads()
app.processEvents()
after = host.ui.download_list.count()
remaining = []
for i in range(after):
    w = host.ui.download_list.itemWidget(host.ui.download_list.item(i))
    remaining.append(w.url)

ok = (sorted(host.download_manager.stopped) == ["active1", "active2"]
      and host.download_manager._task_queue == []
      and sorted(remaining) == ["active1", "active2", "done1"])
report("진행 중 2개는 중지(카드 유지), 대기 중 3개는 제거, 완료는 그대로", ok,
       f"중지={host.download_manager.stopped} 남은카드={remaining} ({before}->{after})")
print(f"        로그: {host.logs[-1]}")

host2 = CancelHost()
host2.resize(1100, 700)
host2.show()
app.processEvents()
it = QListWidgetItem()
w = DownloadItemWidget("done-only", "light")
it.setSizeHint(w.sizeHint())
host2.ui.download_list.addItem(it)
host2.ui.download_list.setItemWidget(it, w)
host2.ui.download_list.item(0).setSelected(True)
app.processEvents()
host2._cancel_selected_downloads()
ok = host2.ui.download_list.count() == 1 and not host2.download_manager.stopped
report("완료 항목만 선택 -> 손대지 않고 안내만", ok, f"로그={host2.logs[-1]}")
host.close(); host2.close()

print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
