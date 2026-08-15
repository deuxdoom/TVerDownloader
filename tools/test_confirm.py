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
print(f"결과 PNG: {OUT}")
print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
