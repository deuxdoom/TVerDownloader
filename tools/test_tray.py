import sys
import winreg

from PyQt6.QtCore import QEventLoop, Qt, QTimer
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

opened_dialog = settings_host.open_settings()
area = QApplication.primaryScreen().availableGeometry()
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
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
