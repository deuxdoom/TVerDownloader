import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QListWidgetItem

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import src.series_parser as sp
from src.qss import build_qss
from src.download_manager import DownloadManager
from src.controllers.download_list import DownloadListController
from src.controllers.library import LibraryController
from src.tray_controller import TrayController
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


class QuietLibrary(LibraryController):
    """목록을 다시 그리는 일만 뺀 library. 검증 대상은 신규 회차 판정뿐이다."""

    def refresh_fav_list(self):
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
        self.library = QuietLibrary(self)

    def append_log(self, text):
        self.logs.append(text)

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
    """스레드를 띄우지 않는 대역. 상태 판별은 진짜 메서드를 그대로 빌려 쓴다."""

    def __init__(self):
        self._active_threads = {}
        self._active_conversions = {}
        self._task_queue = []
        self.stopped = []
        self.stop_all_calls = 0

    def stop_task(self, url):
        self.stopped.append(url)

    def stop_all(self):
        self.stop_all_calls += 1
        stopped = list(self._active_threads) + list(self._active_conversions)
        self.stopped.extend(stopped)
        self._task_queue.clear()
        return len(stopped)

    def remove_task_from_queue(self, url):
        if url in self._task_queue:
            self._task_queue.remove(url)
            return True
        return False

    is_busy = DownloadManager.is_busy
    is_queued = DownloadManager.is_queued
    is_pending = DownloadManager.is_pending


class CancelHost(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = {"theme": "light"}
        self.download_manager = FakeManager()
        self._tray_timer = QTimer(self)
        self.logs = []
        self.download_list = DownloadListController(self)
        self.tray = TrayController(self)
        self.ui.download_list.itemSelectionChanged.connect(self.download_list.sync_cancel_button)
        self.ui.cancel_selected_button.clicked.connect(self.download_list.cancel_selected)

    def append_log(self, text):
        self.logs.append(text)



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
host.download_list.cancel_selected()
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
host2.download_list.cancel_selected()
ok = host2.ui.download_list.count() == 1 and not host2.download_manager.stopped
report("완료 항목만 선택 -> 손대지 않고 안내만", ok, f"로그={host2.logs[-1]}")
host.close(); host2.close()

print()
print("=== 4. 변환 중인 항목도 '진행 중'으로 본다 ===")


def build(states):
    """상태별 카드를 채운 창을 만든다. active=다운로드 중, converting=변환 중."""
    h = CancelHost()
    h.resize(1100, 700)
    h.show()
    app.processEvents()
    for url, state in states:
        it = QListWidgetItem()
        w = DownloadItemWidget(url, "light")
        it.setSizeHint(w.sizeHint())
        h.ui.download_list.addItem(it)
        h.ui.download_list.setItemWidget(it, w)
        if state == "active":
            h.download_manager._active_threads[url] = object()
        elif state == "converting":
            h.download_manager._active_conversions[url] = object()
        elif state == "queued":
            h.download_manager._task_queue.append(url)
    app.processEvents()
    return h


def cards(h):
    return sorted(h.ui.download_list.itemWidget(h.ui.download_list.item(i)).url
                  for i in range(h.ui.download_list.count()))


LAYOUT = [("dl", "active"), ("conv", "converting"), ("wait", "queued"), ("done", "done")]

h = build(LAYOUT)
for i in range(h.ui.download_list.count()):
    h.ui.download_list.item(i).setSelected(True)
h.download_list.delete_selected()
app.processEvents()
report("목록에서 삭제 — 변환 중인 카드는 남긴다", cards(h) == ["conv", "dl"], f"남은카드={cards(h)}")
h.close()

h = build(LAYOUT)
h.download_list.clear_completed()
app.processEvents()
report("완료 항목 삭제 — 변환 중인 카드는 완료가 아니다",
       cards(h) == ["conv", "dl", "wait"], f"남은카드={cards(h)}")
h.close()

h = build(LAYOUT)
for i in range(h.ui.download_list.count()):
    h.ui.download_list.item(i).setSelected(True)
h.download_list.cancel_selected()
app.processEvents()
report("선택 항목 취소 — 변환 중인 것도 중지 대상",
       sorted(h.download_manager.stopped) == ["conv", "dl"],
       f"중지={h.download_manager.stopped} 로그={h.logs[-1]}")
h.close()

h = build(LAYOUT)
h.force_quit = False
h.tray.quit_application()
ok = (h.download_manager.stop_all_calls == 1
      and sorted(h.download_manager.stopped) == ["conv", "dl"]
      and h.force_quit)
report("종료 — stop_all()로 다운로드와 변환을 함께 멈춘다", ok,
       f"중지={h.download_manager.stopped} 로그={h.logs[-1]}")
h.close()

h = build(LAYOUT)
mgr = h.download_manager
checks = [("dl", True, False, True), ("conv", True, False, True),
          ("wait", False, True, True), ("done", False, False, False)]
ok = all((mgr.is_busy(u), mgr.is_queued(u), mgr.is_pending(u)) == (b, q, pnd)
         for u, b, q, pnd in checks)
report("is_busy / is_queued / is_pending 판정", ok,
       " ".join(f"{u}={mgr.is_busy(u):d}{mgr.is_queued(u):d}{mgr.is_pending(u):d}"
                for u, _, _, _ in checks))
h.close()


print()
print("=== 5. 목록 우클릭 메뉴 구성 ===")

import os as _os
from PyQt6.QtGui import QPixmap as _QPixmap, QColor as _QColor
from src.widgets import RoundedMenu as _RoundedMenu

_real_file = _os.path.join(_os.environ.get("TEMP", "."), "tvd-menu-probe.mp4")
open(_real_file, "wb").close()


class MenuHost(CancelHost):
    def __init__(self):
        super().__init__()
        self.config = {"theme": "light", "download_folder": _os.environ.get("TEMP", ".")}

    def play_file(self, path):
        pass



def menu_for(state, thumb, filepath):
    """상태별로 카드를 하나 만들고 우클릭 메뉴 구성을 문자열로 돌려준다."""
    host = MenuHost()
    host.resize(900, 500)
    host.show()
    app.processEvents()
    it = QListWidgetItem()
    w = DownloadItemWidget("probe", "light")
    it.setSizeHint(w.sizeHint())
    host.ui.download_list.addItem(it)
    host.ui.download_list.setItemWidget(it, w)
    if thumb:
        pm = _QPixmap(320, 180)
        pm.fill(_QColor("#3B82F6"))
        w._orig_thumb_pm = pm
    w.final_filepath = filepath
    w.status = {"done": "완료", "error": "오류"}.get(state, "대기")
    if state == "busy":
        host.download_manager._active_threads["probe"] = object()
    if state == "queued":
        host.download_manager._task_queue.append("probe")
    app.processEvents()

    captured = []
    original = _RoundedMenu.exec

    def fake(self, *a, **k):
        captured.extend("----" if x.isSeparator() else x.text() for x in self.actions())
        return None

    _RoundedMenu.exec = fake
    try:
        host.download_list.show_context_menu(host.ui.download_list.visualItemRect(it).center())
    finally:
        _RoundedMenu.exec = original
    host.close()
    return captured


got = menu_for("done", True, _real_file)
report("완료 항목 — 요청한 순서 그대로",
       got == ["목록에서 삭제", "----", "썸네일 다운로드", "파일 재생", "파일 위치 열기"], f"{got}")

got = menu_for("done", False, _real_file)
report("썸네일이 없으면 그 줄만 빠진다",
       got == ["목록에서 삭제", "----", "파일 재생", "파일 위치 열기"], f"{got}")

got = menu_for("busy", True, None)
report("받는 중 — 중지 + 썸네일만", got == ["중지", "----", "썸네일 다운로드"], f"{got}")

got = menu_for("queued", False, None)
report("대기 중 — 뒤에 붙을 것이 없으면 구분선도 없다",
       got == ["대기열에서 제거"], f"{got}")

got = menu_for("error", True, None)
report("오류 — 재다운로드가 맨 앞",
       got == ["재다운로드", "목록에서 삭제", "----", "썸네일 다운로드"], f"{got}")

_os.remove(_real_file)

_FORBIDDEN = DownloadListController.FILENAME_FORBIDDEN
_names = [DownloadListController._safe_filename(x) for x in (f'제목{_FORBIDDEN}끝', "   ...   ", "가" * 300)]
report(f"파일 이름에 못 쓰는 글자 {len(_FORBIDDEN)}개를 걸러낸다",
       not (set(_FORBIDDEN) & set(_names[0])) and _names[1] == "thumbnail" and len(_names[2]) == 80,
       f"{_names[0]!r}, {_names[1]!r}, 길이 {len(_names[2])}")

import inspect as _inspect
from src.widgets import ImagePreviewDialog as _Preview
_preview_src = _inspect.getsource(_Preview)
report("썸네일 확대창에서는 저장 메뉴를 뺐다(목록 메뉴로 옮김)",
       "_save_image" not in _preview_src and "RightButton" not in _preview_src)


print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
