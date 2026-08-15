import os
import sys

from PyQt6.QtCore import QEventLoop, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QSystemTrayIcon

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
import src.dialogs as dialogs_module
from src import shortcuts as S
from src.dialogs import SettingsDialog
from src.qss import build_qss
from src.ui.main_window_ui import MainWindowUI
from src.utils import load_config

T.setup_app_font(app)
T.setup_translations(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []

EP = "https://tver.jp/episodes/ep6hzy79h"
EP2 = "https://tver.jp/episodes/ep0000002"
SR = "https://tver.jp/series/sryhqsa8t0"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle():
    for _ in range(4):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


print("=== 1. 조합표 해석 ===")
report("기본값 4개", set(S.defaults()) == {"open_settings", "toggle_log",
                                          "delete_selected", "clear_search"},
       f"{S.defaults()}")
report("설정이 없으면 기본값", S.resolve({}) == S.defaults())
partial = S.resolve({"shortcuts": {"toggle_log": "ctrl+shift+k"}})
report("적어 둔 것만 갈아끼운다",
       partial["toggle_log"] == "Ctrl+Shift+K" and partial["open_settings"] == "Ctrl+,",
       f"{partial}")
report("대소문자를 가리지 않는다", S.normalize("ctrl+l") == S.normalize("CTRL+L") == "Ctrl+L")
report("빈 값은 사용 안 함으로 남는다",
       S.resolve({"shortcuts": {"clear_search": ""}})["clear_search"] == "")
report("해석 안 되는 값도 사용 안 함",
       S.resolve({"shortcuts": {"toggle_log": "zzz+q"}})["toggle_log"] == "")

report("Ctrl 조합은 입력 중에도 살린다", S.needs_typing_guard("Ctrl+L") is False)
report("맨 키는 입력 중에 꺼야 한다", S.needs_typing_guard("D") is True)
report("Del·Esc도 맨 키", S.needs_typing_guard("Del") and S.needs_typing_guard("Esc"))
report("기능키는 예외", S.needs_typing_guard("F5") is False)
report("빈 조합은 판단 대상 아님", S.needs_typing_guard("") is False)

same_window = S.conflicts({"open_settings": "Ctrl+L", "toggle_log": "Ctrl+L",
                           "delete_selected": "Del", "clear_search": "Esc"})
report("창 단축키끼리 겹치면 잡는다",
       len(same_window) == 1 and set(same_window[0][1]) == {"open_settings", "toggle_log"},
       f"{same_window}")
mixed = S.conflicts({"open_settings": "Del", "toggle_log": "Ctrl+L",
                     "delete_selected": "Del", "clear_search": "Esc"})
report("창 단축키와 목록 단축키가 겹쳐도 잡는다", len(mixed) == 1, f"{mixed}")
disjoint = S.conflicts({"open_settings": "Ctrl+,", "toggle_log": "Ctrl+L",
                        "delete_selected": "Del", "clear_search": "Del"})
report("포커스가 겹치지 않는 범위끼리는 통과", disjoint == [], f"{disjoint}")
report("빈 조합끼리는 겹친 것이 아니다",
       S.conflicts({"open_settings": "", "toggle_log": "",
                    "delete_selected": "Del", "clear_search": "Esc"}) == [])


class Host(QMainWindow):
    """MainWindow에서 단축키·드롭 부분만 떼어 붙인 시험대.

    진짜 MainWindow는 생성자에서 yt-dlp 준비 스레드를 띄운다. 검증하려는 것은
    키와 드롭 처리뿐이라 그 경로를 타지 않게 필요한 조각만 빌려 온다.
    """

    TEXT_ENTRY_TYPES = T.MainWindow.TEXT_ENTRY_TYPES

    def __init__(self, config):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.apply_theme("light")
        self.config = config
        self.logs = []
        self.calls = []
        self._shortcuts = []
        self._guarded_shortcuts = []
        self.setAcceptDrops(True)
        app.focusChanged.connect(self._sync_shortcut_guard)

    def append_log(self, text):
        self.logs.append(text)

    def open_settings(self):
        self.calls.append("open_settings")

    def toggle_log_panel(self):
        self.calls.append("toggle_log")
        self.ui.set_log_visible(not self.ui.is_log_visible())

    def _delete_selected_download_items(self):
        self.calls.append("delete_selected")

    def open_bulk_add(self, initial_urls=None):
        self.calls.append(("bulk", list(initial_urls or [])))

    apply_shortcuts = T.MainWindow.apply_shortcuts
    _shortcut_handler = T.MainWindow._shortcut_handler
    _sync_shortcut_guard = T.MainWindow._sync_shortcut_guard
    _urls_from_mime = T.MainWindow._urls_from_mime
    _accept_dropped_urls = T.MainWindow._accept_dropped_urls
    dragEnterEvent = T.MainWindow.dragEnterEvent
    dragMoveEvent = T.MainWindow.dragMoveEvent
    dropEvent = T.MainWindow.dropEvent


def mime(urls=None, text=None):
    data = QMimeData()
    if urls is not None:
        data.setUrls([QUrl(u) for u in urls])
    if text is not None:
        data.setText(text)
    return data


def drop(host, data):
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, data,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    host.dropEvent(event)
    return event


def drag_enter(host, data):
    event = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, data,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    host.dragEnterEvent(event)
    return event


config = load_config()
config["theme"] = "light"
host = Host(config)
host.resize(1100, 700)
host.show()
host.raise_()
host.activateWindow()
QTest.qWaitForWindowExposed(host)
settle()
host.apply_shortcuts()

print()
print("=== 2. 드롭 판별 ===")
report("uri-list에서 골라낸다", host._urls_from_mime(mime(urls=[EP])) == [EP])
report("텍스트만 있어도 골라낸다", host._urls_from_mime(mime(text=EP)) == [EP])
report("둘 다 실려 와도 한 번만", host._urls_from_mime(mime(urls=[EP], text=EP)) == [EP],
       f"{host._urls_from_mime(mime(urls=[EP], text=EP))}")
report("여러 줄 텍스트를 순서대로",
       host._urls_from_mime(mime(text="\n".join([EP, SR, EP2]))) == [EP, SR, EP2])
report("TVer가 아니면 버린다",
       host._urls_from_mime(mime(urls=["https://www.youtube.com/watch?v=abc"])) == [])
report("섞여 오면 TVer만 남긴다",
       host._urls_from_mime(mime(text="\n".join(["https://example.com", EP, "메모"]))) == [EP])
report("파일을 끌어다 놓으면 무시",
       host._urls_from_mime(mime(urls=["file:///C:/video.mp4"])) == [])
report("사칭 주소는 거른다",
       host._urls_from_mime(mime(text="https://tver.jp.evil.com/episodes/ep1")) == [])

print()
print("=== 3. 드롭 흐름 ===")
report("TVer 주소는 받는다", drag_enter(host, mime(urls=[EP])).isAccepted())
report("아닌 것은 받지 않는다", not drag_enter(host, mime(text="그냥 글")).isAccepted())

host.ui.url_input.clear()
host.calls.clear()
drop(host, mime(urls=[EP]))
settle()
report("하나면 입력창에 채운다", host.ui.url_input.text() == EP,
       f"입력창={host.ui.url_input.text()!r}")
report("대기열로 바로 보내지 않는다", host.calls == [], f"{host.calls}")
report("로그를 남긴다", any("[드롭]" in line for line in host.logs), f"{host.logs[-1:]}")

host.ui.url_input.setText("먼저 적어 둔 내용")
drop(host, mime(urls=[SR]))
settle()
report("끌어다 놓은 주소가 앞선다", host.ui.url_input.text() == SR,
       f"입력창={host.ui.url_input.text()!r}")

host.ui.url_input.clear()
host.calls.clear()
drop(host, mime(text="\n".join([EP, SR, EP2])))
settle()
report("여럿이면 다중 추가로 넘긴다", host.calls == [("bulk", [EP, SR, EP2])], f"{host.calls}")
report("여럿일 때 입력창은 건드리지 않는다", host.ui.url_input.text() == "")

host.calls.clear()
rejected = drop(host, mime(text="아무것도 아님"))
report("주소가 없으면 드롭을 거절", not rejected.isAccepted() and host.calls == [])

print()
print("=== 4. 단축키 연결 ===")
report("5개가 걸린다 (검색칸 2곳 포함)", len(host._shortcuts) == 5,
       f"{[s.key().toString() for s in host._shortcuts]}")
contexts = {s.key().toString(): s.context() for s in host._shortcuts}
report("창 단축키는 창 범위",
       contexts["Ctrl+,"] == Qt.ShortcutContext.WindowShortcut
       and contexts["Ctrl+L"] == Qt.ShortcutContext.WindowShortcut, f"{contexts}")
report("Del·Esc는 위젯 범위",
       contexts["Del"] == Qt.ShortcutContext.WidgetWithChildrenShortcut
       and contexts["Esc"] == Qt.ShortcutContext.WidgetWithChildrenShortcut)

host.calls.clear()
host.ui.download_list.setFocus()
settle()
QTest.keyClick(host.ui.download_list, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)
settle()
report("Ctrl+, 로 설정이 열린다", host.calls == ["open_settings"], f"{host.calls}")

host.calls.clear()
was_visible = host.ui.is_log_visible()
QTest.keyClick(host.ui.download_list, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
settle()
report("Ctrl+L 로 로그 패널이 접힌다",
       host.calls == ["toggle_log"] and host.ui.is_log_visible() is not was_visible,
       f"{host.calls} 보임={host.ui.is_log_visible()}")
QTest.keyClick(host.ui.download_list, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
settle()
report("한 번 더 누르면 다시 펴진다", host.ui.is_log_visible() is was_visible)

host.calls.clear()
QTest.keyClick(host.ui.download_list, Qt.Key.Key_Delete)
settle()
report("목록에서 Del 이 듣는다", host.calls == ["delete_selected"], f"{host.calls}")

host.calls.clear()
host.ui.url_input.setText("지워지면 안 됨")
host.ui.url_input.setFocus()
settle()
QTest.keyClick(host.ui.url_input, Qt.Key.Key_Delete)
settle()
report("입력창에서 Del 은 목록을 건드리지 않는다", host.calls == [], f"{host.calls}")

host.ui.tabs.setCurrentIndex(1)
host.ui.history_search_input.setText("검색어")
host.ui.history_search_input.setFocus()
settle()
QTest.keyClick(host.ui.history_search_input, Qt.Key.Key_Escape)
settle()
report("기록 검색칸에서 Esc 로 비워진다", host.ui.history_search_input.text() == "",
       f"{host.ui.history_search_input.text()!r}")

host.ui.tabs.setCurrentIndex(2)
host.ui.fav_search_input.setText("검색어")
host.ui.fav_search_input.setFocus()
settle()
QTest.keyClick(host.ui.fav_search_input, Qt.Key.Key_Escape)
settle()
report("즐겨찾기 검색칸에서도 Esc 가 듣는다", host.ui.fav_search_input.text() == "")

host.ui.url_input.setText("검색칸이 아니면")
host.ui.url_input.setFocus()
settle()
QTest.keyClick(host.ui.url_input, Qt.Key.Key_Escape)
settle()
report("검색칸이 아닌 입력창은 Esc 로 지워지지 않는다",
       host.ui.url_input.text() == "검색칸이 아니면", f"{host.ui.url_input.text()!r}")

print()
print("=== 5. 조합 변경과 입력 중 보호 ===")
host.config["shortcuts"] = {"open_settings": "D", "toggle_log": "F5",
                            "delete_selected": "Del", "clear_search": ""}
host.apply_shortcuts()
settle()
report("비운 조합은 아예 만들지 않는다", len(host._shortcuts) == 3,
       f"{[s.key().toString() for s in host._shortcuts]}")

host.calls.clear()
host.ui.download_list.setFocus()
settle()
QTest.keyClick(host.ui.download_list, Qt.Key.Key_D)
settle()
report("바꾼 조합이 목록에서 동작한다", host.calls == ["open_settings"], f"{host.calls}")

host.calls.clear()
host.ui.url_input.clear()
host.ui.url_input.setFocus()
settle()
QTest.keyClick(host.ui.url_input, Qt.Key.Key_D)
settle()
report("입력 중에는 맨 키를 가로채지 않는다",
       host.calls == [] and host.ui.url_input.text() != "",
       f"호출={host.calls} 입력창={host.ui.url_input.text()!r}")

host.calls.clear()
QTest.keyClick(host.ui.url_input, Qt.Key.Key_F5)
settle()
report("기능키는 입력 중에도 듣는다", host.calls == ["toggle_log"], f"{host.calls}")

host.calls.clear()
host.ui.download_list.setFocus()
settle()
QTest.keyClick(host.ui.download_list, Qt.Key.Key_Escape)
settle()
report("비운 검색 단축키는 반응이 없다", host.calls == [])

report("툴팁에 지금 조합이 붙는다", "(D)" in host.ui.settings_button.toolTip(),
       f"{host.ui.settings_button.toolTip()!r}")
host.config["shortcuts"] = S.defaults()
host.apply_shortcuts()
report("조합을 되돌리면 툴팁도 되돌아온다",
       host.ui.settings_button.toolTip().count("(") == 1
       and "Ctrl+," in host.ui.settings_button.toolTip(),
       f"{host.ui.settings_button.toolTip()!r}")

print()
print("=== 6. 입력창 Enter ===")
source = (_bootstrap.ROOT / "TVerDownloader.py").read_text(encoding="utf-8")
report("Enter가 다운로드에 연결돼 있다",
       "self.ui.url_input.returnPressed.connect(self.process_input_url)" in source)
entered = []
host.ui.url_input.returnPressed.connect(lambda: entered.append(1))
host.ui.url_input.setText(EP)
host.ui.url_input.setFocus()
settle()
QTest.keyClick(host.ui.url_input, Qt.Key.Key_Return)
settle()
report("Enter 를 누르면 실제로 신호가 나온다", entered == [1], f"{entered}")
host.close()

print()
print("=== 7. 설정창 단축키 탭 ===")


class FakeBox:
    """모달 경고창이 뜨면 검증이 멈춘다. 호출 사실만 받아 둔다."""

    warnings = []

    @staticmethod
    def warning(*args, **kwargs):
        FakeBox.warnings.append(args[1] if len(args) > 1 else "")


real_box = dialogs_module.QMessageBox
dialogs_module.QMessageBox = FakeBox

for theme in ("light", "dark"):
    app.setStyleSheet(build_qss(theme))
    cfg = load_config()
    cfg["theme"] = theme
    dialog = SettingsDialog(cfg, None)
    dialog.resize(760, 620)
    dialog.show()
    settle()
    dialog.nav.setCurrentRow(dialog._shortcut_page_row)
    settle()
    editors = dialog.shortcut_edits
    report(f"[{theme}] 네 동작이 모두 보인다",
           len(editors) == 4 and all(e.isVisible() for e in editors.values()),
           f"{list(editors)}")
    report(f"[{theme}] 저장된 조합이 채워져 있다",
           editors["open_settings"].keySequence().toString() == "Ctrl+,",
           f"{editors['open_settings'].keySequence().toString()!r}")
    dialog.grab().save(f"{OUT}/shortcuts_settings_{theme}.png")

    editors["toggle_log"].setKeySequence(QKeySequence("Ctrl+,"))
    settle()
    report(f"[{theme}] 겹치면 그 자리에서 알린다", dialog.shortcut_warning.text() != "",
           f"{dialog.shortcut_warning.text()!r}")
    FakeBox.warnings.clear()
    dialog._save_settings()
    report(f"[{theme}] 겹친 채로는 저장되지 않는다",
           len(FakeBox.warnings) == 1
           and dialog.result() != QDialog.DialogCode.Accepted.value,
           f"경고={FakeBox.warnings} 결과={dialog.result()}")
    report(f"[{theme}] 충돌한 탭으로 옮겨 준다",
           dialog.nav.currentRow() == dialog._shortcut_page_row)

    editors["toggle_log"].setKeySequence(QKeySequence("Ctrl+Shift+K"))
    editors["clear_search"].clear()
    settle()
    report(f"[{theme}] 고치면 경고가 사라진다", dialog.shortcut_warning.text() == "")
    dialog._save_settings()
    saved = load_config()
    report(f"[{theme}] 바꾼 조합이 저장된다",
           saved["shortcuts"]["toggle_log"] == "Ctrl+Shift+K"
           and saved["shortcuts"]["clear_search"] == "",
           f"{saved.get('shortcuts')}")

    reopened = SettingsDialog(load_config(), None)
    report(f"[{theme}] 다시 열면 그 값이 보인다",
           reopened.shortcut_edits["toggle_log"].keySequence().toString() == "Ctrl+Shift+K")
    reopened._reset_shortcuts()
    report(f"[{theme}] 기본값 되돌리기가 듣는다",
           reopened._shortcut_table() == S.defaults(), f"{reopened._shortcut_table()}")
    reopened._save_settings()
    report(f"[{theme}] 되돌린 값이 저장된다", load_config()["shortcuts"] == S.defaults())
    reopened.close()
    dialog.close()

dialogs_module.QMessageBox = real_box
if os.path.exists("downloader_config.json"):
    os.remove("downloader_config.json")

print()
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
