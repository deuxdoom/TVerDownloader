import pathlib
import sys
import winreg

from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src import autostart
from src.dialogs import SettingsDialog
from src.qss import build_qss
from src.ui import main_window_ui as ui_module
from src.ui.main_window_ui import MainWindowUI
from src.utils import load_config, localized_app_name
from src.widgets import RoundedMenu

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []

TEST_VALUE = "TVerDownloader_ToolsTest"
FAKE_EXE = r'"C:\Fake\TVerDownloader.exe" --tray'


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle():
    for _ in range(4):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


def stored_value(name):
    """Run 키에 실제로 들어 있는 값. 없으면 None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


class Host(QMainWindow):
    """MainWindow에서 트레이 부분만 떼어 붙인 시험대."""

    def __init__(self, config):
        super().__init__()
        self.tray_icon = QSystemTrayIcon(self)
        self.ui = MainWindowUI(self)
        self.ui.setup_ui()
        self.ui.setup_tray("3.2.0")
        self.ui.apply_theme("light")
        self.config = config
        self.logs = []
        self.calls = []

    def append_log(self, text):
        self.logs.append(text)

    def bring_to_front(self):
        self.calls.append("restore")

    def quit_application(self):
        self.calls.append("quit")

    def open_settings(self):
        self.calls.append("settings")

    set_autostart = T.MainWindow.set_autostart
    set_always_on_top = T.MainWindow.set_always_on_top


class SettingsHost(QMainWindow):
    """트레이에 들어가 있는 상태에서 설정 창을 여는 경로만 재현한다.

    진짜 open_settings는 exec()로 멈춰 서므로, 뜬 창을 그 안에서 재고 닫는다.
    """

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logs = []

    def append_log(self, text):
        self.logs.append(text)

    _pull_to_front = staticmethod(T.MainWindow._pull_to_front)
    _center_on_cursor_screen = staticmethod(T.MainWindow._center_on_cursor_screen)
    _place_dialog = T.MainWindow._place_dialog

    def open_settings(self):
        measured = {}
        dialog = SettingsDialog(self.config, self)
        QTimer.singleShot(0, lambda: self._place_dialog(dialog))

        def probe():
            measured["visible"] = dialog.isVisible()
            measured["geometry"] = dialog.frameGeometry()
            measured["active"] = dialog.isActiveWindow()
            dialog.reject()

        QTimer.singleShot(140, probe)
        dialog.exec()
        return measured


print("=== 1. 소스로 돌릴 때는 잠가 둔다 ===")
report("frozen이 아니면 등록할 명령이 없다", autostart.target_command() is None)
report("supported()가 False", autostart.supported() is False)
report("is_enabled()도 False로 떨어진다", autostart.is_enabled() is False)
report("set_enabled()가 레지스트리를 건드리지 않는다",
       autostart.set_enabled(True) is False and stored_value(autostart.VALUE_NAME) is None,
       f"실제 값={stored_value(autostart.VALUE_NAME)!r}")

print()
print("=== 2. 등록 켜고 끄기 (시험용 값 이름으로) ===")
real_name, real_command = autostart.VALUE_NAME, autostart.target_command
autostart.VALUE_NAME = TEST_VALUE
autostart.target_command = lambda: FAKE_EXE
try:
    report("켜면 Run 키에 명령이 들어간다",
           autostart.set_enabled(True) and stored_value(TEST_VALUE) == FAKE_EXE,
           f"{stored_value(TEST_VALUE)!r}")
    report("켠 뒤에는 is_enabled()가 True", autostart.is_enabled() is True)
    report("명령에 --tray가 붙어 있다", autostart.TRAY_FLAG in (stored_value(TEST_VALUE) or ""))

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, TEST_VALUE, 0, winreg.REG_SZ,
                          r'"D:\Moved\TVerDownloader.exe" --tray')
    report("경로가 다른 값이 들어 있으면 꺼진 것으로 본다", autostart.is_enabled() is False)
    report("다시 켜면 지금 경로로 갱신된다",
           autostart.set_enabled(True) and stored_value(TEST_VALUE) == FAKE_EXE)

    report("끄면 값이 사라진다",
           autostart.set_enabled(False) and stored_value(TEST_VALUE) is None)
    report("이미 꺼져 있어도 성공으로 본다", autostart.set_enabled(False) is True)
finally:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, TEST_VALUE)
        except FileNotFoundError:
            pass
    autostart.VALUE_NAME, autostart.target_command = real_name, real_command

report("시험용 값이 남지 않았다", stored_value(TEST_VALUE) is None)
report("진짜 값도 건드리지 않았다", stored_value(real_name) is None,
       f"{stored_value(real_name)!r}")

print()
print("=== 3. 트레이로 시작하기 ===")
report("--tray가 붙으면 창을 띄우지 않는다",
       autostart.launched_for_tray(["TVerDownloader.exe", "--tray"]) is True)
report("그냥 실행하면 창을 띄운다",
       autostart.launched_for_tray(["TVerDownloader.exe"]) is False)

config = load_config()
config["theme"] = "light"
host = Host(config)
host.set_always_on_top(True, init=True)
settle()
report("시작 중 항상 위 설정이 창을 먼저 띄우지 않는다", not host.isVisible())
host.show()
settle()
host.set_always_on_top(False, init=True)
settle()
report("이미 떠 있으면 플래그를 바꿔도 그대로 보인다", host.isVisible())

print()
print("=== 4. 메뉴 구성 ===")
menu = host.tray_icon.contextMenu()
report("RoundedMenu를 쓴다", isinstance(menu, RoundedMenu))
report("창 배경이 투명이라 모서리가 둥글게 나온다",
       menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))

actions = [a for a in menu.actions() if not a.isSeparator()]
labels = [a.text() for a in actions]
report("항목이 다섯", len(actions) == 5, f"{labels}")
report("첫 항목이 '<앱 이름> 열기'",
       labels[0] == f"{localized_app_name()} 열기", f"{labels[0]!r}")
report("눌러도 되는 줄임을 문구로 알린다", labels[0].endswith("열기"), f"{labels[0]!r}")
report("첫 항목만 굵게", actions[0].font().bold()
       and not any(a.font().bold() for a in actions[1:]))
report("나머지 문구",
       labels[1:] == ["윈도우 시작 시 실행", "GitHub 페이지", "설정", "프로그램 종료"],
       f"{labels[1:]}")
report("설정이 종료 바로 위", labels.index("설정") == labels.index("프로그램 종료") - 1)
separators = [i for i, a in enumerate(menu.actions()) if a.isSeparator()]
report("구분선은 둘만", len(separators) == 2, f"{len(separators)}개")
report("여는 항목과 그 아래를 가른다", separators[0] == 1, f"{separators}")
report("종료만 따로 떼어 둔다",
       separators[1] == len(menu.actions()) - 2, f"{separators}")
report("시작 프로그램만 체크 항목",
       actions[1].isCheckable()
       and not any(a.isCheckable() for a in (actions[0], actions[2], actions[3], actions[4])))
report("소스에서는 시작 프로그램이 잠겨 있다", not actions[1].isEnabled())

host.calls.clear()
actions[0].trigger()
report("첫 항목이 창을 되살린다", host.calls == ["restore"], f"{host.calls}")

opened = []
real_open = ui_module.webbrowser.open
ui_module.webbrowser.open = lambda url: opened.append(url)
try:
    actions[2].trigger()
finally:
    ui_module.webbrowser.open = real_open
report("GitHub 항목이 프로젝트 페이지를 연다",
       opened == ["https://github.com/deuxdoom/TVerDownloader"], f"{opened}")

host.calls.clear()
actions[3].trigger()
report("설정 항목이 설정 창을 부른다", host.calls == ["settings"], f"{host.calls}")

host.calls.clear()
actions[4].trigger()
report("종료 항목이 확인창 없이 바로 종료한다", host.calls == ["quit"], f"{host.calls}")
report("종료 경로에 확인창이 없다",
       "confirm" not in T.MainWindow.quit_application.__code__.co_names,
       f"{T.MainWindow.quit_application.__code__.co_names}")

print()
print("=== 5. 체크 표시는 레지스트리를 다시 읽는다 ===")
actions[1].setEnabled(True)
actions[1].blockSignals(True)
actions[1].setChecked(True)
actions[1].blockSignals(False)
host.ui.sync_autostart_check()
report("실제 상태가 아니면 되돌린다", not actions[1].isChecked())

host.logs.clear()
host.set_autostart(True)
report("등록에 실패하면 로그로 알린다",
       any("[오류]" in line for line in host.logs), f"{host.logs}")
report("표시도 실제 상태로 되돌린다", not actions[1].isChecked())

print()
print("=== 6. 트레이에 내려둔 채로 설정 열기 ===")
settings_host = SettingsHost(load_config())
settings_host.resize(1100, 700)
settings_host.show()
settle()
settings_host.showMinimized()
settle()
settings_host.hide()
settle()
report("메인 창이 트레이에 내려가 있다", not settings_host.isVisible())

area = QApplication.primaryScreen().availableGeometry()
QCursor.setPos(area.center())
settle()
"""마우스를 주 화면 가운데에 놓고 잰다.

`_center_on_cursor_screen`은 마우스가 있는 화면을 고르므로, 그대로 두면 결과가
'검사를 돌릴 때 마우스가 어느 모니터에 있었나'에 달린다. 실제로 자동화가 마우스를
보조 모니터에 두고 간 뒤 이 검사가 실패했다. 그 화면이 대화상자보다 작으면 가운데가
아니라 안쪽으로 밀어 넣는 것이 맞는 동작이라 더 헷갈린다.
"""
opened_dialog = settings_host.open_settings()
placed = opened_dialog["geometry"]
report("설정 창이 떴다", opened_dialog["visible"], f"{opened_dialog}")
report("앞으로 끌어냈다", opened_dialog["active"])
report("왼쪽 위 구석에 붙지 않는다", placed.topLeft() != area.topLeft(),
       f"{placed.getRect()}")
report("화면 가운데에 놓인다",
       abs(placed.center().x() - area.center().x()) <= 1
       and abs(placed.center().y() - area.center().y()) <= 1,
       f"창중심={placed.center().x()},{placed.center().y()} "
       f"화면중심={area.center().x()},{area.center().y()}")
report("작업 표시줄과 겹치지 않는다", area.contains(placed),
       f"{placed.getRect()} in {area.getRect()}")
report("메인 창은 그대로 내려가 있다", not settings_host.isVisible())
settings_host.deleteLater()

shown_host = SettingsHost(load_config())
shown_host.resize(1100, 700)
shown_host.show()
settle()
shown_placed = shown_host.open_settings()["geometry"]
report("창이 떠 있으면 자리를 건드리지 않는다",
       shown_host.frameGeometry().contains(shown_placed.center()),
       f"대화상자중심={shown_placed.center().x()},{shown_placed.center().y()} "
       f"창={shown_host.frameGeometry().getRect()}")
shown_host.close()
shown_host.deleteLater()
settle()

print()
print("=== 7. 렌더 ===")
for theme in ("light", "dark"):
    app.setStyleSheet(build_qss(theme))
    host.ui.apply_theme(theme)
    for checked in (False, True):
        actions[1].blockSignals(True)
        actions[1].setChecked(checked)
        actions[1].blockSignals(False)
        settle()
        menu.grab().save(f"{OUT}/tray_menu_{theme}_{'on' if checked else 'off'}.png")
    report(f"[{theme}] 메뉴가 그려진다", menu.grab().width() > 0)

host.close()
host.deleteLater()
settle()

print()
print("=== 둥근 메뉴 창 속성 ===")

from PyQt6.QtGui import QAction as _QAction
from src.widgets import RoundedMenu as _RoundedMenu

probe = _RoundedMenu()
flags = probe.windowFlags()
report("투명 배경 — QSS가 그린 둥근 모양을 창 모양으로 삼는다",
       probe.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
report("Frameless — 빠지면 모서리 바깥이 까맣게 찍힌다(화면 실측 밝기 0)",
       bool(flags & Qt.WindowType.FramelessWindowHint))
report("NoDropShadow — 그림자 없이 테두리만",
       bool(flags & Qt.WindowType.NoDropShadowWindowHint))

plain = _RoundedMenu()
plain.addAction("목록에서 삭제")
plain.addAction("파일 위치 열기")
plain.aboutToShow.emit()
report("체크할 것이 없으면 글자 앞자리를 비우지 않는다",
       plain.property("checkmarks") is False, f"checkmarks={plain.property('checkmarks')}")

checked = _RoundedMenu()
checked.addAction("열기")
_a = _QAction("윈도우 시작 시 실행", checked, checkable=True)
checked.addAction(_a)
checked.aboutToShow.emit()
report("체크 항목이 있으면 자리를 지킨다",
       checked.property("checkmarks") is True, f"checkmarks={checked.property('checkmarks')}")

late = _RoundedMenu()
_b = _QAction("나중에 켜는 항목", late)
late.addAction(_b)
late.aboutToShow.emit()
before = late.property("checkmarks")
_b.setCheckable(True)
late.aboutToShow.emit()
report("항목을 넣은 뒤 checkable을 켜도 열 때 다시 본다",
       before is False and late.property("checkmarks") is True,
       f"{before} -> {late.property('checkmarks')}")

_qss = build_qss("light")
report("기본 여백은 좁고, 체크 쓰는 메뉴만 넓힌다",
       'QMenu[checkmarks="true"]::item' in _qss and "8px 18px 8px 34px" not in _qss)


print()
print("=== 입력칸 우클릭 메뉴 아이콘 ===")

from PyQt6.QtWidgets import QLineEdit as _QLineEdit
from PyQt6.QtGui import QColor as _QColor
from src.icons import is_monochrome_white as _is_white
from src.qss import palette as _palette


def _icon_colors(action):
    """아이콘에서 불투명한 화소들의 색을 모아 온다."""
    img = action.icon().pixmap(16, 16).toImage()
    return [img.pixelColor(x, y) for y in range(img.height()) for x in range(img.width())
            if img.pixelColor(x, y).alpha() > 200]


_probe_edit = _QLineEdit()
_probe_edit.setText("샘플")

_raw = _probe_edit.createStandardContextMenu()
_white = [a.text().split("	")[0].replace("&", "") for a in _raw.actions()
          if not a.isSeparator() and not a.icon().isNull() and _is_white(a.icon())]
report("Qt가 주는 편집 아이콘은 흰색 단색이다(문제의 원인)",
       len(_white) == 7, f"흰 아이콘 {len(_white)}개: {_white}")
_raw.deleteLater()

for _theme in ("light", "dark"):
    _tinter = T.setup_menu_icons(app, _theme)
    _menu = _probe_edit.createStandardContextMenu()
    _tinter._tint(_menu)
    _want = _QColor(_palette(_theme)["text"])
    _checked = []
    _bad = []
    for _a in _menu.actions():
        if _a.isSeparator() or _a.icon().isNull():
            continue
        _px = _icon_colors(_a)
        _name = _a.text().split("	")[0].replace("&", "")
        _checked.append(_name)
        if not _px or not all(abs(c.red() - _want.red()) < 4
                              and abs(c.green() - _want.green()) < 4
                              and abs(c.blue() - _want.blue()) < 4 for c in _px):
            _bad.append(_name)
    report(f"[{_theme}] 아이콘이 테마 글자색으로 칠해진다",
           len(_checked) == 7 and not _bad,
           f"{len(_checked)}개 확인, 어긋남={_bad}")
    _menu.deleteLater()
    app.removeEventFilter(_tinter)

_tinter = T.setup_menu_icons(app, "light")
_menu = _probe_edit.createStandardContextMenu()
_tinter._tint(_menu)
_first = [a for a in _menu.actions() if not a.icon().isNull()][0]
_key_before = _first.icon().cacheKey()
_tinter._tint(_menu)
report("이미 칠한 아이콘은 다시 칠하지 않는다",
       _first.icon().cacheKey() == _key_before)

_tinter.set_color(_palette("dark")["text"])
_tinter._tint(_menu)
_px = _icon_colors(_first)
_want = _QColor(_palette("dark")["text"])
report("테마가 바뀌면 색도 따라간다",
       bool(_px) and abs(_px[0].red() - _want.red()) < 4,
       f"#{_px[0].red():02X}{_px[0].green():02X}{_px[0].blue():02X}" if _px else "없음")

from src.appicon import get_app_icon as _app_icon
report("색이 든 아이콘은 건드리지 않는다", not _is_white(_app_icon()))

_sizes_before = set((s.width(), s.height()) for s in _first.icon().availableSizes())
report("칠한 뒤에도 크기 종류가 그대로다", len(_sizes_before) >= 2, f"{sorted(_sizes_before)}")

_src = pathlib.Path("TVerDownloader.py").read_text(encoding="utf-8")
report("실행 진입점에서 감시자를 건다", "setup_menu_icons(app, theme)" in _src)
report("테마를 바꿀 때 색을 갱신한다", "tinter.set_color(palette(theme)" in _src)

print()
print("=== Qt가 만든 입력칸 메뉴도 우리 메뉴와 같은 모양 ===")

_shape = T.MenuShapeGuard(app)
app.installEventFilter(_shape)
_qt_menu = _probe_edit.createStandardContextMenu()
_qt_menu.ensurePolished()
_ours = RoundedMenu()
_ours.addAction("샘플")
_ours.ensurePolished()

HINTS = ((Qt.WindowType.FramelessWindowHint, "Frameless"),
         (Qt.WindowType.NoDropShadowWindowHint, "NoDropShadow"))
for _flag, _label in HINTS:
    report(f"입력칸 메뉴에 {_label}가 걸린다", bool(_qt_menu.windowFlags() & _flag))
report("입력칸 메뉴가 투명 배경을 쓴다",
       _qt_menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
report("우리 메뉴와 창 힌트가 같다",
       (_qt_menu.windowFlags() & (HINTS[0][0] | HINTS[1][0]))
       == (_ours.windowFlags() & (HINTS[0][0] | HINTS[1][0])),
       f"입력칸={int(_qt_menu.windowFlags()):#x} 우리={int(_ours.windowFlags()):#x}")
report("항목은 Qt가 만든 그대로 남는다", len(_qt_menu.actions()) >= 6,
       f"{[a.text() for a in _qt_menu.actions() if a.text()]}")
report("Polish에서 건다(Show면 창이 숨겨져 메뉴가 뜨지 않는다)",
       "QEvent.Type.Polish" in pathlib.Path("TVerDownloader.py").read_text(encoding="utf-8")
       .split("class MenuShapeGuard")[1].split("def setup_menu_icons")[0])
report("실행 진입점에서 모양 감시자도 건다", "MenuShapeGuard(app)" in _src)

app.removeEventFilter(_shape)
_qt_menu.deleteLater()
_ours.deleteLater()

_menu.deleteLater()
_probe_edit.deleteLater()

for _m in (probe, plain, checked, late):
    _m.deleteLater()
settle()

print()
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
