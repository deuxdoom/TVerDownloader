import os
import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src.bulk_dialog import BulkAddDialog
from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.utils import load_config, match_tver_url

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle():
    for _ in range(4):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


print("=== 1. URL 판별 ===")
ACCEPT = [
    "https://tver.jp/episodes/ep6hzy79h",
    "https://tver.jp/series/sryhqsa8t0",
    "http://tver.jp/episodes/ep123",
    "https://www.tver.jp/episodes/ep123",
    "  https://tver.jp/episodes/ep123  ",
    "https://tver.jp/episodes/ep123?utm_source=x",
    "https://tver.jp/series/sr123#top",
]
REJECT = [
    "",
    "그냥 복사한 텍스트",
    "https://tver.jp/",
    "https://tver.jp/mypage",
    "https://tver.jp/episodes/",
    "https://www.youtube.com/watch?v=abc",
    "https://tver.jp.evil.com/episodes/ep123",
    "여기 보세요 https://tver.jp/episodes/ep123 재밌어요",
    "비밀번호: hunter2",
    "C:\\Users\\Eric\\Documents",
]
for s in ACCEPT:
    report(f"수락: {s.strip()[:46]}", match_tver_url(s) == s.strip())
for s in REJECT:
    report(f"거절: {(s[:44] or '(빈 문자열)')}", match_tver_url(s) is None)

print()
print("=== 2. 설정 기본값 ===")
cfg = load_config()
report("clipboard_watch 기본 OFF", cfg.get("clipboard_watch") is False,
       f"{cfg.get('clipboard_watch')!r}")

print()
print("=== 3. 감시 동작 ===")


class Host(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = {"theme": "light"}
        self.logs = []
        self._clipboard_connected = False
        self._last_clipboard_url = ""
        self._bulk_dialog = None
        self.bulk_calls = []
        self.bulk_opens = True

    def append_log(self, text):
        self.logs.append(text)

    def open_bulk_add(self, initial_urls=None):
        """진짜 창은 exec()로 멈춰 서므로, 무엇을 들고 불렸는지만 받아 둔다."""
        self.bulk_calls.append(list(initial_urls or []))
        return self.bulk_opens

    apply_clipboard_watch = T.MainWindow.apply_clipboard_watch
    _on_clipboard_changed = T.MainWindow._on_clipboard_changed


clip = QGuiApplication.clipboard()
host = Host()
host.resize(1100, 700)
host.show()
settle()

EP = "https://tver.jp/episodes/ep6hzy79h"
SR = "https://tver.jp/series/sryhqsa8t0"

report("기본은 연결 안 됨", host._clipboard_connected is False)
clip.setText(EP); settle()
report("꺼진 상태에서는 입력창이 그대로", host.ui.url_input.text() == "",
       f"입력창={host.ui.url_input.text()!r}")

host.apply_clipboard_watch(True)
report("켜면 연결됨", host._clipboard_connected is True)

clip.setText(""); settle()
host.ui.url_input.clear(); host._last_clipboard_url = ""
clip.setText(EP); settle()
report("에피소드 주소가 입력창에 들어간다", host.ui.url_input.text() == EP,
       f"입력창={host.ui.url_input.text()!r}")
report("로그를 남긴다", any("클립보드" in l for l in host.logs), f"{host.logs[-1:]}")

host.ui.url_input.clear()
clip.setText(EP); settle()
report("같은 주소가 다시 와도 무시", host.ui.url_input.text() == "",
       f"입력창={host.ui.url_input.text()!r}")

host.ui.url_input.clear()
clip.setText(SR); settle()
report("시리즈 주소도 다운로드 입력창으로", host.ui.url_input.text() == SR,
       f"입력창={host.ui.url_input.text()!r}")
report("즐겨찾기 칸은 건드리지 않는다", host.ui.fav_input.text() == "",
       f"즐겨찾기칸={host.ui.fav_input.text()!r}")

host.ui.url_input.setText("직접 입력한 내용")
host._last_clipboard_url = ""
clip.setText(EP); settle()
report("입력창에 내용이 있으면 덮어쓰지 않는다",
       host.ui.url_input.text() == "직접 입력한 내용",
       f"입력창={host.ui.url_input.text()!r}")

host.ui.url_input.clear(); host._last_clipboard_url = ""
before = host.ui.url_input.text()
clip.setText("아무 텍스트나 복사"); settle()
report("TVer 주소가 아니면 아무 반응 없음", host.ui.url_input.text() == before,
       f"입력창={host.ui.url_input.text()!r}")

print()
print("=== 4. 끄면 실제로 감시하지 않는가 ===")
host.apply_clipboard_watch(False)
report("연결 해제됨", host._clipboard_connected is False)

probe = {"hits": 0}
original = host._on_clipboard_changed


def counting():
    probe["hits"] += 1
    original()


host._on_clipboard_changed = counting
host.ui.url_input.clear(); host._last_clipboard_url = ""
clip.setText("https://tver.jp/episodes/ep-after-off"); settle()
report("끈 뒤에는 콜백이 아예 불리지 않는다", probe["hits"] == 0 and host.ui.url_input.text() == "",
       f"호출={probe['hits']}회 입력창={host.ui.url_input.text()!r}")
host._on_clipboard_changed = original

print()
print("=== 5. 반복 토글 안정성 ===")
for _ in range(3):
    host.apply_clipboard_watch(True)
    host.apply_clipboard_watch(True)
    host.apply_clipboard_watch(False)
    host.apply_clipboard_watch(False)
report("중복 호출에도 상태가 어긋나지 않음", host._clipboard_connected is False)
host.apply_clipboard_watch(True)
host.ui.url_input.clear(); host._last_clipboard_url = ""
clip.setText("https://tver.jp/episodes/ep-final"); settle()
report("다시 켜면 정상 동작", host.ui.url_input.text() == "https://tver.jp/episodes/ep-final",
       f"입력창={host.ui.url_input.text()!r}")

print()
print("=== 6. 두 번째 주소는 다중 추가 창으로 ===")
EP2 = "https://tver.jp/episodes/ep0000002"
EP3 = "https://tver.jp/episodes/ep0000003"


def reset(input_text=""):
    host.ui.url_input.setText(input_text)
    host._last_clipboard_url = ""
    host._bulk_dialog = None
    host.bulk_calls.clear()
    host.logs.clear()
    clip.setText(""); settle()
    host._last_clipboard_url = ""


reset(EP)
clip.setText(EP2); settle()
report("입력창에 주소가 있으면 둘을 모아 창을 연다",
       host.bulk_calls == [[EP, EP2]], f"{host.bulk_calls}")
report("넘긴 주소는 입력창에서 비운다", host.ui.url_input.text() == "",
       f"입력창={host.ui.url_input.text()!r}")
report("무슨 일이 일어났는지 로그로 알린다",
       any("다중 추가" in line for line in host.logs), f"{host.logs}")

reset(EP)
host.bulk_opens = False
clip.setText(EP2); settle()
report("창을 못 열면 원래 주소를 되돌려 놓는다", host.ui.url_input.text() == EP,
       f"입력창={host.ui.url_input.text()!r}")
host.bulk_opens = True

reset(EP)
clip.setText(EP); settle()
report("입력창과 같은 주소면 창을 열지 않는다",
       host.bulk_calls == [] and host.ui.url_input.text() == EP, f"{host.bulk_calls}")

reset("직접 적던 메모")
clip.setText(EP2); settle()
report("TVer 주소가 아닌 글은 여전히 건드리지 않는다",
       host.bulk_calls == [] and host.ui.url_input.text() == "직접 적던 메모",
       f"{host.bulk_calls} 입력창={host.ui.url_input.text()!r}")

print()
print("=== 7. 창이 열려 있는 동안 한 줄씩 ===")
reset()
dialog = BulkAddDialog(host, [EP, EP2])
host._bulk_dialog = dialog
report("미리 채운 목록이 그대로 들어간다", dialog.get_urls() == [EP, EP2], f"{dialog.get_urls()}")

clip.setText(EP3); settle()
report("복사하면 창 끝에 쌓인다", dialog.get_urls() == [EP, EP2, EP3], f"{dialog.get_urls()}")
report("입력창은 건드리지 않는다", host.ui.url_input.text() == "",
       f"입력창={host.ui.url_input.text()!r}")
report("창에 넣었다고 로그를 남긴다",
       any("다중 추가 창에 넣었습니다" in line for line in host.logs), f"{host.logs}")

host._last_clipboard_url = ""
clip.setText(EP2); settle()
report("이미 있는 주소는 다시 넣지 않는다", dialog.get_urls() == [EP, EP2, EP3],
       f"{dialog.get_urls()}")

host.logs.clear()
host._last_clipboard_url = ""
clip.setText("주소가 아닌 글"); settle()
report("주소가 아니면 창도 그대로", dialog.get_urls() == [EP, EP2, EP3] and host.logs == [])

report("빈 창에 넣으면 첫 줄이 된다", BulkAddDialog(host).append_url(EP) is True)
empty = BulkAddDialog(host)
empty.append_url(EP)
report("빈 줄이 섞여도 한 줄에 하나로 정리된다",
       (empty.text.setPlainText(f"{EP}\n\n\n{EP2}\n") or empty.append_url(EP3))
       and empty.get_urls() == [EP, EP2, EP3], f"{empty.get_urls()}")
dialog.close(); empty.close()
host._bulk_dialog = None

host.apply_clipboard_watch(False)
host.close()

if os.path.exists("downloader_config.json"):
    os.remove("downloader_config.json")
QTimer.singleShot(80, app.quit)
app.exec()
print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
