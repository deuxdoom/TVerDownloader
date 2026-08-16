import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QLabel

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
import src.message as message
from src.qss import build_qss

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []

LONG = "이미 다운로드한 항목입니다:\n\nテスト番組 第12話 とても長いタイトル\n\n다시 다운로드할까요?"
SHORT = "종료하시겠습니까?"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def centers(box):
    """본문 라벨과 버튼 줄의 가로 중심을 잰다.

    아이콘도 QLabel이라 글이 든 것 중에서 가장 넓은 것을 본문으로 본다.
    """
    buttons = box.findChild(QDialogButtonBox)
    text = max((w for w in box.findChildren(QLabel) if w.text()),
               key=lambda w: w.width())
    return text.geometry().center().x(), buttons.geometry().center().x()


def shot(theme, text, icon_name, color_key, tag):
    """확인 창을 띄운 상태에서 재고, 그림으로도 남긴다.

    exec()가 중첩 이벤트 루프라 그 안에서 재야 실제로 보이는 배치가 나온다.
    """
    app.setStyleSheet(build_qss(theme))
    measured = {}

    def probe():
        box = app.activeModalWidget()
        for _ in range(3):
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
        measured["values"] = centers(box)
        measured["size"] = (box.width(), box.height())
        box.grab().save(f"{OUT}/confirm_{tag}_{theme}.png")
        box.reject()

    QTimer.singleShot(120, probe)
    message.confirm(None, "확인", text, icon_name=icon_name,
                    color_key=color_key, theme=theme)
    return measured


for theme in ("light", "dark"):
    got = shot(theme, LONG, "download", "accent", "dup")
    text_x, button_x = got["values"]
    report(f"[{theme}] 중복 다운로드 창의 글과 버튼이 같은 중심",
           abs(text_x - button_x) <= 1, f"글={text_x} 버튼={button_x} 창={got['size']}")

    got = shot(theme, SHORT, "info", "danger", "short")
    text_x, button_x = got["values"]
    report(f"[{theme}] 짧은 문구에서도 중심이 같다",
           abs(text_x - button_x) <= 1, f"글={text_x} 버튼={button_x} 창={got['size']}")

print()
print("=== confirm_with_link / confirm_single — 닫는 길이 살아 있는가 ===")

from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt


def drive(kind, steps, theme="light"):
    """창을 띄우고 steps를 차례로 눌러 본다. (반환값, 링크 횟수, 단계 기록).

    **창이 스스로 닫혔는지만 본다.** 예전 검사는 Esc를 보낸 뒤 곧바로 reject()를
    불러서, Esc가 먹지 않아도 그 뒷줄이 창을 닫아 주는 바람에 통과했다. 그래서
    X가 비활성이고 Esc가 죽은 것을 놓쳤다. 보조 장치는 마지막 안전장치로만 둔다.
    """
    opened = []
    state = {"box": None, "log": []}
    original = message._ConfirmBox.showEvent

    def capture(self, event):
        state["box"] = self
        original(self, event)

    def press(index):
        box = state["box"]
        if box is None or not box.isVisible():
            return
        how = steps[index]
        if how == "esc":
            box.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape.value,
                                        Qt.KeyboardModifier.NoModifier))
        elif how == "x":
            box.close()
        else:
            for b in box.buttons():
                if b.text() == how:
                    b.click()
                    break
        state["log"].append(f"{how}->{'열림' if box.isVisible() else '닫힘'}")

    def rescue():
        box = state["box"]
        if box is not None and box.isVisible():
            state["log"].append("(강제로 닫음)")
            box._closing = True
            box.hide()

    message._ConfirmBox.showEvent = capture
    for i in range(len(steps)):
        QTimer.singleShot(150 + i * 200, lambda i=i: press(i))
    QTimer.singleShot(150 + len(steps) * 200 + 250, rescue)
    try:
        if kind == "link":
            got = message.confirm_with_link(
                None, "새 버전 확인",
                "새 버전 v3.4.0이(가) 나왔습니다.\n\n지금 받아서 바로 적용할 수 있습니다.",
                yes_text="지금 업데이트", link_text="내역 확인",
                on_link=lambda: opened.append(1), icon_name="download", theme=theme)
        else:
            got = message.confirm_single(
                None, "새 버전 확인",
                "새 버전 v3.4.0이(가) 나왔습니다.\n\n지금 받아서 바로 적용할 수 있습니다.",
                ok_text="자동 업데이트", icon_name="download", theme=theme)
    finally:
        message._ConfirmBox.showEvent = original
    app.processEvents()
    return got, len(opened), state["log"]


for kind, ok_text in (("link", "지금 업데이트"), ("single", "자동 업데이트")):
    got, opened, log = drive(kind, [ok_text])
    report(f"[{kind}] '{ok_text}'를 누르면 True로 닫힌다",
           got is True and opened == 0 and "강제" not in " ".join(log), f"{log}")

    got, opened, log = drive(kind, ["esc"])
    report(f"[{kind}] Esc로 창이 닫힌다", got is False and "esc->닫힘" in log,
           f"{log} — 안 닫히면 창이 갇힌다")

    got, opened, log = drive(kind, ["x"])
    report(f"[{kind}] X로 창이 닫힌다", got is False and "x->닫힘" in log,
           f"{log} — Reject 역할을 아무 데도 안 주면 Qt가 X를 잠근다")

got, opened, log = drive("link", ["내역 확인"])
report("'내역 확인'은 링크를 열고 창을 남긴다", opened == 1 and "내역 확인->열림" in log,
       f"{log} — 내용을 보고 나서 받을지 정할 수 있어야 한다")

got, opened, log = drive("link", ["내역 확인", "지금 업데이트"])
report("내역을 본 뒤 그대로 업데이트할 수 있다", got is True and opened == 1, f"{log}")

got, opened, log = drive("link", ["내역 확인", "esc"])
report("내역을 본 뒤 닫아도 갇히지 않는다", got is False and "esc->닫힘" in log,
       f"{log} — clickedButton이 남아 있어 Esc를 링크로 오해하면 여기서 갇힌다")

got, opened, log = drive("link", ["내역 확인", "내역 확인", "esc"])
report("여러 번 눌러도 그때마다 열고 닫을 수 있다", opened == 2 and "esc->닫힘" in log, f"{log}")

print()
print("=== 제목 표시줄 X가 실제로 켜져 있는가 ===")

import ctypes

SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x0
MF_GRAYED = 0x1
MF_DISABLED = 0x2
MENU_ITEM_MISSING = 0xFFFFFFFF

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetSystemMenu.argtypes = (ctypes.c_void_p, ctypes.c_bool)
user32.GetSystemMenu.restype = ctypes.c_void_p
user32.GetMenuState.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)
user32.GetMenuState.restype = ctypes.c_uint


def close_button_state(box):
    """윈도우에 직접 물어 제목 표시줄 X가 잠겼는지 본다.

    **눌러 보는 것으로는 이 고장을 못 잡는다.** 위의 x 항목이 쓰는 box.close()는
    closeEvent로 곧장 들어가므로, Qt가 X를 잠가 둔 상태에서도 창이 닫히고 통과한다.
    실제로 이번 고장이 그 틈으로 새어 나갔다 — 검사는 모두 초록인데 사용자가 누른
    X는 죽어 있었다. 잠김 여부는 시스템 메뉴의 SC_CLOSE 항목에만 남는다.

    **진짜 클릭을 흉내 내지는 않는다.** SC_CLOSE를 창에 보내는 방법은 모달 루프가
    풀리는 시점과 얽혀 검사가 그대로 멈췄다(실측: 3분을 넘겨 강제 종료). 잠금만
    읽으면 그 위험이 없고, 닫히는 동작은 위의 x 항목이 이미 보고 있어 둘을 합치면
    두 경로가 다 덮인다.

    argtypes를 지정하는 이유는 handle이 64비트여서다. ctypes 기본 restype은 32비트
    int이라 HMENU가 잘려 엉뚱한 값이 오고, 그러면 늘 '항목 없음'으로 보인다.
    """
    menu = user32.GetSystemMenu(int(box.winId()), False)
    if not menu:
        return "시스템 메뉴 없음"
    state = user32.GetMenuState(menu, SC_CLOSE, MF_BYCOMMAND)
    if state == MENU_ITEM_MISSING:
        return "항목 없음"
    if state & (MF_GRAYED | MF_DISABLED):
        return "잠김"
    return "켜짐"


def peek(kind):
    """창을 띄운 채로 X의 상태만 재고 닫는다. 창을 잡는 방식은 drive()와 같다."""
    state = {"box": None, "value": None}
    original = message._ConfirmBox.showEvent

    def capture(self, event):
        state["box"] = self
        original(self, event)

    def read():
        box = state["box"]
        if box is None or not box.isVisible():
            return
        for _ in range(3):
            app.processEvents()
        state["value"] = close_button_state(box)
        box.reject()

    def rescue():
        box = state["box"]
        if box is not None and box.isVisible():
            box._closing = True
            box.hide()

    message._ConfirmBox.showEvent = capture
    QTimer.singleShot(150, read)
    QTimer.singleShot(600, rescue)
    try:
        if kind == "link":
            message.confirm_with_link(None, "새 버전 확인", "본문",
                                      yes_text="지금 업데이트", link_text="내역 확인",
                                      on_link=lambda: None, icon_name="download",
                                      theme="light")
        else:
            message.confirm_single(None, "새 버전 확인", "본문",
                                   ok_text="자동 업데이트", icon_name="download",
                                   theme="light")
    finally:
        message._ConfirmBox.showEvent = original
    app.processEvents()
    return state["value"]


for kind in ("link", "single"):
    got = peek(kind)
    report(f"[{kind}] 제목 표시줄 X가 켜져 있다", got == "켜짐",
           f"{got} — Reject 역할이 어디에도 없으면 Qt가 X를 잠근다(실측)")

print()
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
