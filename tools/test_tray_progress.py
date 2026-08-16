import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.download_manager import DownloadManager
from src.tray_controller import TrayController
from src.threads.download_thread import DownloadThread
from src.utils import item_percent
from src.appicon import (app_icon_with_progress, get_app_icon,
                         _content_pixmap, TRAY_ICON_SIZES)

app.setStyleSheet(build_qss("light"))
results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


print("=== 1. 항목 진행률 정리 ===")

cases = [
    (0, 0, 0),
    (37.5, 0, 37),
    (100, 0, 100),
    (None, 42, 42),
    ("nope", 42, 42),
    (150, 0, 100),
    (-10, 50, 0),
]
ok = True
for pct, prev, expect in cases:
    got = item_percent(pct, prev)
    if got != expect:
        ok = False
        print(f"        {pct}/{prev} -> {got}, 기대 {expect}")
report("값이 없거나 이상하면 이전 값 유지, 나머지는 0~100으로 자른다", ok, f"{len(cases)}건")


print()
print("=== 1-2. 조각 나눠 받기 (yt-dlp 실제 출력으로 재생) ===")


def fake_thread():
    """스레드를 띄우지 않고 줄 해석만 돌린다."""
    t = DownloadThread.__new__(DownloadThread)
    t.url = "u"; t._final_filepath = ""; t._thumbnail_embed_failed = False
    t._parts = DownloadThread.DEFAULT_PARTS
    t._part_index = -1; t._aside = False; t._current_component = ""
    t._sidecar_paths = set()
    seen = []

    class Sig:
        def emit(self, url, payload):
            seen.append(payload)

    t.progress = Sig()
    return t, seen


def prog(pct, of="100.00MiB"):
    return f"[download]  {pct}% of  {of} at   10.00MiB/s ETA 00:10"


def replay(lines):
    """줄들을 흘려보내고 화면에 찍힐 진행률 순서를 돌려준다."""
    t, seen = fake_thread()
    for line in lines:
        t._parse_line(line)
    t.progress.emit("u", {"status": "완료", "percent": 100})
    value = 0
    track = []
    for payload in seen:
        value = item_percent(payload.get("percent"), value)
        if "percent" in payload:
            track.append(value)
    return t, track


MERGED = (["[info] x: Downloading 1 format(s): 401+251",
           "[download] Destination: /t/v.f401.mp4"] + [prog(p) for p in (0, 50, 100)]
          + ["[download] Destination: /t/v.f251.webm"] + [prog(p) for p in (0, 100)]
          + ['[Merger] Merging formats into "/t/v.webm"'])

SINGLE = (["[info] x: Downloading 1 format(s): 18",
           "[download] Destination: /t/v.mp4"] + [prog(p) for p in (0, 30, 40, 50, 80, 100)])

TRAILING = MERGED + ["[download] Destination: /t/v.en.vtt"] + [prog(p, "12.00KiB") for p in (0, 100)]

NO_INFO = (["[download] Destination: /t/v.f401.mp4"] + [prog(p) for p in (0, 50, 100)]
           + ["[download] Destination: /t/v.f251.webm"] + [prog(p) for p in (0, 100)])

LEADING_SUB = (["[info] x: Downloading subtitles: ja",
                "[info] x: Downloading 1 format(s): hls-3400-1+hls-ts_AUDIO-0_2-pro_16ddc4",
                "[info] Writing video subtitles to: /t/v.ja.vtt",
                "[download] Destination: /t/v.ja.vtt"]
               + [prog(p, "34.20KiB") for p in (2.9, 43.9, 100.0)]
               + ["[download] Destination: /t/v.fhls-3400-1.mp4"]
               + [prog(p) for p in (0, 50, 100)]
               + ["[download] Destination: /t/v.fhls-ts_AUDIO-0_2-pro_16ddc4.mp4"]
               + [prog(p) for p in (0, 100)]
               + ['[Merger] Merging formats into "/t/v.mp4"'])
"""자막이 있는 TVer 드라마의 실제 출력 순서. 자막이 본편보다 먼저 온다."""

for name, lines, parts in [("영상+소리 따로(401+251)", MERGED, 2),
                           ("한 파일로(18) — 유튜브에서 50%에 멈추던 경우", SINGLE, 1),
                           ("본편 뒤 자막까지 받는 경우", TRAILING, 2),
                           ("format 줄을 못 본 경우(예전 방식으로 후퇴)", NO_INFO, 2),
                           ("자막을 본편보다 먼저 받는 경우", LEADING_SUB, 2)]:
    t, track = replay(lines)
    good = track == sorted(track) and track[-1] == 100 and t._parts == parts
    report(name, good, f"조각 {t._parts}개, 진행률 {track}")

t, track = replay(SINGLE)
report("한 파일이면 구성 요소 이름을 붙이지 않는다", t._current_component == "",
       f"component={t._current_component!r}")

t, _ = replay(MERGED)
report("둘로 나뉘면 마지막이 '오디오'로 남는다", t._current_component == "오디오",
       f"component={t._current_component!r}")

t, _ = replay(TRAILING)
report("본편 뒤 딸려오는 파일은 진행률 보고를 멈춘다", t._aside)

t, sub_track = replay(LEADING_SUB)
report("본편보다 먼저 오는 자막은 진행바를 밀지 않는다",
       sub_track == [0, 25, 50, 50, 100, 100], f"진행률 {sub_track}")

t, seen = fake_thread()
for line in LEADING_SUB:
    t._parse_line(line)
first_named = next((p.get("component") for p in seen if p.get("component")), None)
report("자막 뒤에 오는 본편이 '비디오'로 잡힌다", first_named == "비디오",
       f"첫 구성 요소={first_named!r}")

t, _ = fake_thread()
for line in LEADING_SUB[:4]:
    t._parse_line(line)
report("자막 파일을 최종 파일로 오해하지 않는다", t._final_filepath == "",
       f"final={t._final_filepath!r}")


print()
print("=== 2. 묶음 전체 진행률 ===")


def mgr_with(active=(), converting=(), queued=(), done=()):
    """상태별 URL을 채운 관리자를 만든다. active는 (url, percent) 쌍."""
    m = DownloadManager({}, None)
    for url, pct in active:
        m._active_threads[url] = object()
        m._item_percent[url] = pct
        m._active_urls.add(url)
    for url in converting:
        m._active_conversions[url] = object()
        m._item_percent[url] = 100
        m._active_urls.add(url)
    for url in queued:
        m._task_queue.append(url)
        m._active_urls.add(url)
    for url in done:
        m._active_urls.add(url)
    return m


report("아무것도 없으면 None", mgr_with().overall_progress() is None)

m = mgr_with(active=[("a", 40)])
report("한 개만 받는 중이면 그 값", m.overall_progress() == 40, f"{m.overall_progress()}")

m = mgr_with(active=[("a", 40), ("b", 60)])
report("두 개면 평균", m.overall_progress() == 50, f"{m.overall_progress()}")

m = mgr_with(active=[("a", 100)], queued=["b", "c", "d"])
report("대기 중인 항목은 0으로 센다", m.overall_progress() == 25, f"{m.overall_progress()}")

m = mgr_with(active=[("a", 50)], done=["b"])
report("끝난 항목은 100으로 남는다", m.overall_progress() == 75, f"{m.overall_progress()}")

m = mgr_with(converting=["a"], queued=["b"])
report("변환 중은 100(받기는 끝남)", m.overall_progress() == 50, f"{m.overall_progress()}")

before = mgr_with(active=[("a", 90), ("b", 20)])
after = mgr_with(active=[("b", 20)], done=["a"])
report("항목이 끝나도 전체 진행률이 뒤로 가지 않는다",
       after.overall_progress() >= before.overall_progress(),
       f"{before.overall_progress()}% -> {after.overall_progress()}%")

m = mgr_with(active=[("a", 100)], done=["b", "c"])
report("100을 넘지 않는다", m.overall_progress() == 100, f"{m.overall_progress()}")


print()
print("=== 3. 진행률 추적과 정리 ===")

m = DownloadManager({}, None)
m._active_urls.add("u")
m._on_progress("u", {"component": "비디오", "percent": 60, "log": "x"})
report("_on_progress가 진행률을 기록한다(payload 값이 곧 전체 기준)",
       m._item_percent.get("u") == 60, f"{m._item_percent}")

m._on_progress("u", {"status": "후처리 중 (병합)"})
report("진행률 없는 payload는 값을 지우지 않는다", m._item_percent.get("u") == 60,
       f"{m._item_percent}")

m._active_urls.clear()
m._check_completion()
report("묶음이 끝나면 진행률도 비운다", not m._item_percent, f"{m._item_percent}")

m = DownloadManager({}, None)
m._active_urls.add("u"); m._item_percent["u"] = 40
m.reset_for_redownload("u")
report("재다운로드 준비하면 이전 진행률을 버린다", "u" not in m._item_percent)

m = DownloadManager({}, None)
m._item_percent["u"] = 40
m.stop_all()
report("stop_all()이 진행률을 비운다", not m._item_percent)


print()
print("=== 4. 트레이 툴팁 ===")


class Host(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = {"theme": "light"}
        self.download_manager = DownloadManager({}, None)
        self.tray = TrayController(self)
        self.logs = []
        self.ui.setup_tray("3.3.0")

    def bring_to_front(self):
        pass

    def quit_application(self):
        pass

    def open_settings(self):
        pass

    def set_autostart(self, enabled):
        pass

    def append_log(self, text):
        self.logs.append(text)



h = Host()
tip = h.tray_icon.toolTip()
report("놀고 있을 때는 이름만", "\n" not in tip and "대기" not in tip, repr(tip))

h.ui.update_tray_status(3, 1, 42)
tip = h.tray_icon.toolTip()
ok = tip.count("\n") == 1 and "3 대기 / 1 진행" in tip and "42%" in tip
report("받는 중에는 개수와 진행률을 함께", ok, repr(tip))

h.ui.update_tray_status(2, 0, None)
tip = h.tray_icon.toolTip()
report("진행률이 없으면 개수만", "2 대기 / 0 진행" in tip and "%" not in tip, repr(tip))

queued_only = Host()
for u in ("q1", "q2", "q3"):
    queued_only.download_manager._active_urls.add(u)
    queued_only.download_manager._task_queue.append(u)
queued_only.tray.on_queue_changed(3, 0)
tip = queued_only.tray_icon.toolTip()
ok = ("3 대기 / 0 진행" in tip and "%" not in tip
      and queued_only.tray_icon.icon().pixmap(16, 16).toImage()
      == get_app_icon().pixmap(16, 16).toImage())
report("줄만 서 있고 시작 전이면 0%도 고리도 붙이지 않는다", ok, repr(tip))
queued_only.tray_icon.hide(); queued_only.close(); queued_only.deleteLater()

h.ui.update_tray_status(0, 0, None)
report("다 끝나면 이름만으로 되돌아간다", "대기" not in h.tray_icon.toolTip(),
       repr(h.tray_icon.toolTip()))

h.download_manager._active_urls.add("a")
h.download_manager._active_threads["a"] = object()
h.download_manager._item_percent["a"] = 70
h.tray.on_queue_changed(0, 1)
ok = h.ui.queue_count_label.text() == "0 대기 / 1 진행" and "70%" in h.tray_icon.toolTip()
report("queue_changed 하나로 라벨과 트레이가 함께 갱신된다", ok,
       f"라벨={h.ui.queue_count_label.text()!r} 툴팁={h.tray_icon.toolTip()!r}")

h.download_manager._on_progress("a", {"component": "오디오", "percent": 90})
h.tray.refresh_status(); h.tray._sync()
report("progress_updated 뒤 진행률이 따라 올라간다", "90%" in h.tray_icon.toolTip(),
       repr(h.tray_icon.toolTip()))

h.download_manager._on_progress("a", {"status": "후처리 중 (병합)"})
h.tray.refresh_status(); h.tray._sync()
report("진행률 없는 갱신이 와도 값이 떨어지지 않는다", "90%" in h.tray_icon.toolTip(),
       repr(h.tray_icon.toolTip()))


print()
print("=== 5. 진행률 고리 ===")


def opaque_ratio(pixmap):
    """픽스맵에서 실제로 칠해진 화소 비율. 고리가 그려졌는지 가늠한다."""
    image = pixmap.toImage()
    total = image.width() * image.height()
    filled = sum(1 for y in range(image.height()) for x in range(image.width())
                 if image.pixelColor(x, y).alpha() > 40)
    return filled / total if total else 0


plain = get_app_icon().pixmap(16, 16)
ring0 = app_icon_with_progress(0).pixmap(16, 16)
ring100 = app_icon_with_progress(100).pixmap(16, 16)

report("None이면 원래 아이콘 그대로",
       app_icon_with_progress(None).pixmap(16, 16).toImage() == plain.toImage())
report("고리가 붙으면 원래 아이콘과 다르다", ring0.toImage() != plain.toImage())
report("0%와 100%는 다르게 보인다", ring0.toImage() != ring100.toImage())

available = {(s.width(), s.height()) for s in app_icon_with_progress(50).availableSizes()}
report(f"고리를 크기 {len(TRAY_ICON_SIZES)}종으로 미리 그려 둔다",
       available == {(s, s) for s in TRAY_ICON_SIZES}, f"{sorted(available)}")

report("150% 배율이 요구하는 24·30px을 실제로 갖고 있다",
       {(24, 24), (30, 30)} <= available)

dpr_pm = app_icon_with_progress(50).pixmap(16, 16)
report("16px 자리 요청이 배율만큼 큰 그림으로 돌아온다(줄여 쓰지 않는다)",
       dpr_pm.width() == int(16 * dpr_pm.devicePixelRatio()),
       f"{dpr_pm.width()}px dpr={dpr_pm.devicePixelRatio()}")

ratios = [opaque_ratio(app_icon_with_progress(p).pixmap(24, 24)) for p in (0, 50, 100)]
report("채울수록 칠해진 면적이 늘어난다", ratios[0] < ratios[1] < ratios[2],
       " -> ".join(f"{r:.3f}" for r in ratios))

crop = _content_pixmap()
crop_img = crop.toImage()


def edge_has_paint(img, side):
    """자른 그림의 한 변에 칠해진 화소가 닿아 있는지."""
    w, h = img.width(), img.height()
    if side == "top":
        return any(img.pixelColor(x, 0).alpha() > 8 for x in range(w))
    if side == "bottom":
        return any(img.pixelColor(x, h - 1).alpha() > 8 for x in range(w))
    if side == "left":
        return any(img.pixelColor(0, y).alpha() > 8 for y in range(h))
    return any(img.pixelColor(w - 1, y).alpha() > 8 for y in range(h))


sides = {s: edge_has_paint(crop_img, s) for s in ("top", "bottom", "left", "right")}
report("앱 아이콘의 투명 여백을 걷어낸다(네 변 모두 그림이 닿음)", all(sides.values()),
       f"{crop.width()}x{crop.height()} {sides}")

base_img = get_app_icon().pixmap(64, 64).toImage()
top_pad = next(y for y in range(base_img.height())
               if any(base_img.pixelColor(x, y).alpha() > 8 for x in range(base_img.width())))
bottom_pad = next(y for y in range(base_img.height())
                  if any(base_img.pixelColor(x, base_img.height() - 1 - y).alpha() > 8
                         for x in range(base_img.width())))
report("원본은 위아래 여백이 달라 그대로 쓰면 치우친다(크롭이 필요한 이유)",
       top_pad != bottom_pad, f"위 {top_pad}px / 아래 {bottom_pad}px")

bad = app_icon_with_progress(999).pixmap(16, 16)
report("100을 넘겨도 죽지 않고 꽉 찬 고리", bad.toImage() == ring100.toImage())
report("음수도 0으로 막는다",
       app_icon_with_progress(-5).pixmap(16, 16).toImage() == ring0.toImage())


print()
print("=== 6. 1초 간격 제한 ===")

h2 = Host()
h2.download_manager._active_urls.add("a")
h2.download_manager._active_threads["a"] = object()
h2.download_manager._item_percent["a"] = 10

calls = []
real_update = h2.ui.update_tray_status


def counting(queued, active, percent=None):
    calls.append(percent)
    real_update(queued, active, percent)


h2.ui.update_tray_status = counting

h2.tray.on_queue_changed(0, 1)
report("첫 갱신은 기다리지 않고 바로", len(calls) == 1, f"{calls}")
report("도는 동안 타이머가 돈다", h2.tray._timer.isActive())

for pct in (20, 30, 40, 50, 60):
    h2.download_manager._item_percent["a"] = pct
    h2.tray.refresh_status()
report("사이에 들어온 갱신은 쌓이지 않는다", len(calls) == 1, f"{calls}")

h2.tray._sync()
report("타이머가 돌면 마지막 값 하나만 반영", calls == [10, 60], f"{calls}")

h2.tray._sync()
report("바뀐 것이 없으면 트레이를 건드리지 않는다", calls == [10, 60], f"{calls}")

h2.download_manager._active_threads.clear()
h2.download_manager._active_urls.clear()
h2.tray.on_queue_changed(0, 0)
ok = calls[-1] is None and not h2.tray._timer.isActive()
report("다 끝나면 기다리지 않고 원래 아이콘으로", ok,
       f"{calls} 타이머={h2.tray._timer.isActive()}")
report("되돌린 아이콘이 원래 것과 같다",
       h2.tray_icon.icon().pixmap(16, 16).toImage() == plain.toImage())
h2.tray_icon.hide(); h2.close(); h2.deleteLater()


def teardown():
    h.tray_icon.hide()
    h.close()
    h.deleteLater()
    app.processEvents()


teardown()
print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
