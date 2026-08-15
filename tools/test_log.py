import sys

from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src.download_manager import DownloadManager
from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.utils import load_config

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle():
    for _ in range(4):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


class Host(QMainWindow):
    """MainWindow에서 로그 출력 부분만 떼어 붙인 시험대.

    진짜 MainWindow는 생성자에서 준비 스레드를 띄운다. 보려는 것은 로그 한 줄이
    어떻게 그려지는지뿐이라 그 경로를 타지 않게 필요한 조각만 빌려 온다.
    """

    LOG_RULE_MAX = T.MainWindow.LOG_RULE_MAX

    def __init__(self, config):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = config

    append_log = T.MainWindow.append_log
    append_heading = T.MainWindow.append_heading
    append_notice = T.MainWindow.append_notice
    toggle_theme = T.MainWindow.toggle_theme
    toggle_log_panel = T.MainWindow.toggle_log_panel
    apply_theme = T.MainWindow.apply_theme
    _log_text_width = T.MainWindow._log_text_width
    _log_heading = T.MainWindow._log_heading
    _rule_matching = T.MainWindow._rule_matching
    _as_html = staticmethod(T.MainWindow._as_html)
    _scroll_log_to_end = T.MainWindow._scroll_log_to_end


def teardown(*windows):
    """app이 살아 있는 동안 창을 정리한다.

    파이썬이 끝난 뒤 Qt 위젯이 파괴되면 이벤트 루프가 없어 이따금 segfault로 끝난다.
    무해한 잔여 현상이지만 종료 코드가 139가 되어 검증 결과를 가린다.
    """
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


def wraps(host, line: str) -> bool:
    """그 줄이 로그 폭 안에서 접히는지 본다.

    QTextEdit이 실제로 몇 줄로 쪼갰는지는 블록의 layout에게 물어야 한다. 글자
    폭을 따로 더해서 비교하면 줄바꿈 규칙이 빠져 실제와 어긋난다.
    """
    log = host.ui.log_output
    log.clear()
    host.append_log(line)
    settle()
    block = log.document().findBlockByNumber(0)
    return block.layout().lineCount() > 1


config = load_config()
config["theme"] = "light"
host = Host(config)
host.resize(1100, 700)
host.show()
settle()

print("=== 1. 구분선이 한 줄에 들어간다 ===")
log = host.ui.log_output
usable = host._log_text_width()
print(f"        로그 패널={host.ui.LOG_PANE_WIDTH}px 글이 들어가는 폭={usable}px")

for title in ("다운로드 시작", "안내", "긴 제목을 넣어도 접히지 않아야 한다"):
    head = host._log_heading(title)
    width = log.fontMetrics().horizontalAdvance(head)
    report(f"'{title}' 구분선이 접히지 않는다",
           not wraps(host, head) and width <= usable,
           f"괘선 {(len(head) - len(title) - 2) // 2}개씩 · {width}px")

report("예전 고정값(12개)이었다면 넘쳤을 것",
       log.fontMetrics().horizontalAdvance(f"{'─' * 12} 다운로드 시작 {'─' * 12}") > usable,
       f"{log.fontMetrics().horizontalAdvance(f'{chr(9472) * 12} 다운로드 시작 {chr(9472) * 12}')}px")
report("짧은 제목은 예전 모습 그대로",
       host._log_heading("안내") == f"{'─' * 12} 안내 {'─' * 12}",
       host._log_heading("안내"))

print()
print("=== 2. 스크롤바가 생겨도 그대로 ===")
log.clear()
head = host._log_heading("다운로드 시작")
host.append_heading("다운로드 시작", "https://tver.jp/episodes/ep6hzy79h")
for i in range(200):
    host.append_log(f"채우는 줄 {i}")
settle()
report("스크롤바가 떴다", log.verticalScrollBar().isVisible())
report("먼저 찍힌 구분선이 다시 접히지 않는다",
       log.document().findBlockByNumber(0).layout().lineCount() == 1,
       f"{log.document().findBlockByNumber(0).layout().lineCount()}줄")

print()
print("=== 3. 로그 패널을 접은 채로 시작해도 ===")
folded = Host(load_config())
folded.resize(1100, 700)
folded.ui.set_log_visible(False)
folded.show()
settle()
folded_head = folded._log_heading("다운로드 시작")
report("접힌 채로 만든 구분선도 같은 길이", folded_head == head,
       f"접힘={len(folded_head)} 펼침={len(head)}")
folded.ui.set_log_visible(True)
settle()
report("펴 보아도 접히지 않는다", not wraps(folded, folded_head))

print()
print("=== 4. 화면에 바로 보이는 조작은 로그에 남기지 않는다 ===")
log.clear()
host.toggle_theme()
host.toggle_log_panel()
settle()
report("테마 전환·패널 토글은 조용하다", log.toPlainText() == "",
       f"{log.toPlainText()!r}")
report("영상 재생은 실패했을 때만 로그를 남긴다",
       T.MainWindow.play_file.__code__.co_names.count("append_log") == 1,
       f"{T.MainWindow.play_file.__code__.co_names}")

print()
print("=== 5. 다운로드 시작 안내를 만드는 쪽 ===")
manager = DownloadManager(load_config(), None)
received = []
manager.heading.connect(lambda title, body: received.append((title, body)))
manager._on_progress("https://tver.jp/episodes/ep6hzy79h", {"log": "[download] 0%"})
manager._on_progress("https://tver.jp/episodes/ep6hzy79h", {"log": "[download] 5%"})
report("다운로드 시작은 한 번만 알린다",
       received == [("다운로드 시작", "https://tver.jp/episodes/ep6hzy79h")], f"{received}")
report("괘선을 직접 그리지 않는다",
       "─" not in (_bootstrap.ROOT / "src" / "download_manager.py").read_text(encoding="utf-8"))

print()
print("=== 6. 렌더 ===")
for theme in ("light", "dark"):
    host.apply_theme(theme, persist=False)
    log.clear()
    host.append_notice("안내", ["TVer는 일본 지역 제한이 있습니다.",
                                "원활한 다운로드를 위해 일본 VPN을 켜고 사용해주세요."])
    host.append_heading("다운로드 시작", "https://tver.jp/episodes/ep6hzy79h")
    host.append_log("[성공] 다운로드 완료: C:/video/테스트 번組.mp4")
    settle()
    host.ui.log_pane.grab().save(f"{OUT}/log_pane_{theme}.png")
    metrics = log.fontMetrics()
    rule_lines = [t for t in log.toPlainText().splitlines() if "─" in t]
    report(f"[{theme}] 괘선이 든 줄이 모두 한 줄로 떨어진다",
           len(rule_lines) == 3
           and all(metrics.horizontalAdvance(t) <= usable for t in rule_lines),
           f"{[metrics.horizontalAdvance(t) for t in rule_lines]} <= {usable}")

teardown(host, folded)

print()
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
