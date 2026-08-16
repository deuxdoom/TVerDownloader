"""정보 창 — 단추 구성과 업데이트 확인 흐름.

단추가 링크 모양(LinkButton)이던 것을 보통 단추로 바꿨다. 눌러도 되는 것인지
분명하지 않다는 것이 이유였으므로, 다시 링크로 돌아가지 않게 여기서 못 박는다.

**눌러서 하는 확인은 최신이어도 반드시 무언가 알려야 한다.** 시작할 때 도는
확인은 새 버전이 없으면 조용히 지나가는데, 그 성질을 그대로 가져오면 눌렀는데
아무 일도 안 일어난 것처럼 보인다.

렌더 확인은 두지 않는다. 창을 여러 번 만들었다 지우면 이벤트 루프 없이 위젯을
무더기로 파괴하게 되어, CLAUDE.md가 적어 둔 무해한 잔재로 종료 코드가 더럽혀진다.
모양은 필요할 때 눈으로 본다.

가로채는 자리를 조심한다. updater는 `from src.message import confirm`으로 이름을
끌어와 쓰므로 message 쪽을 갈아 끼워도 소용이 없다. updater 네임스페이스를 바꾼다.
네트워크는 타지 않는다.
"""
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap

_bootstrap.setup()

import TVerDownloader as T
import src.about_dialog as about_mod
import src.updater as updater
from src import self_update
from src.about_dialog import AboutDialog
from src.qss import build_qss

T.setup_app_font(app)
app.setStyleSheet(build_qss("light"))
OUT = _bootstrap.OUT_DIR
results = []

VERSION = "3.3.0"


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def run_check(release, theme="light", shot=None):
    """업데이트 확인 단추를 눌러 보고 (반응 목록, 단추 이름들)을 돌려준다."""
    seen = []
    saved = (updater.fetch_latest, updater.confirm, updater.confirm_single,
             updater.confirm_with_link, updater.notify, about_mod.notify)

    def rec(kind):
        def fake(parent, title, text, **kwargs):
            seen.append((kind, title))
            return False
        return fake

    updater.fetch_latest = lambda log=print: release
    updater.confirm = rec("confirm")
    updater.confirm_single = rec("confirm")
    updater.confirm_with_link = rec("confirm")
    updater.notify = rec("notify")
    about_mod.notify = rec("notify")

    dialog = AboutDialog(VERSION, None, theme)
    buttons = dialog.findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    check = next(b for b in buttons if b.text() == AboutDialog.CHECK_LABEL)

    def press():
        if shot:
            dialog.grab().save(f"{OUT}/about_{shot}.png")
        check.click()

    QTimer.singleShot(150, press)
    QTimer.singleShot(2200, lambda: dialog.isVisible() and dialog.reject())
    dialog.exec()
    for _ in range(20):
        app.processEvents()

    (updater.fetch_latest, updater.confirm, updater.confirm_single,
     updater.confirm_with_link, updater.notify, about_mod.notify) = saved
    dialog.deleteLater()
    app.processEvents()
    return seen, labels, check


print("=== 1. 단추 구성 ===")
seen, labels, _ = run_check({"tag_name": "v3.3.0", "assets": []})
report("네 단추가 요청한 순서대로 있다",
       labels == ["제작자 유투브", "문의하기", AboutDialog.CHECK_LABEL, "닫기"], f"{labels}")

dialog = AboutDialog(VERSION, None, "light")
link_styled = [b.text() for b in dialog.findChildren(QPushButton)
               if b.objectName() == "LinkButton"]
report("링크 모양 단추가 남아 있지 않다", link_styled == [],
       f"{link_styled} — 보통 단추여야 눌러도 되는 것으로 보인다")
dialog.deleteLater()
app.processEvents()

print()
print("=== 1-2. 단추 크기와 호버 색 ===")

from src.qss import ABOUT_BUTTON_SCALE, palette

size_dialog = AboutDialog(VERSION, None, "light")
size_dialog.show()
for _ in range(5):
    app.processEvents()
heights = {b.objectName() or b.text(): b.height()
           for b in size_dialog.findChildren(QPushButton)}
close_h = heights.get("닫기", 0)
left = [heights[n] for n in ("AboutYouTube", "AboutContact", "AboutUpdate")]
ratios = [h / close_h for h in left] if close_h else []
report("왼쪽 단추 셋이 닫기보다 10~20% 작다",
       bool(ratios) and all(0.80 <= r <= 0.90 for r in ratios),
       f"닫기={close_h}px 왼쪽={left} 비율={[f'{r:.0%}' for r in ratios]}"
       f" (기준 {ABOUT_BUTTON_SCALE:.0%})")
size_dialog.hide()
size_dialog.deleteLater()
app.processEvents()

for theme in ("light", "dark"):
    css = build_qss(theme)
    colors = palette(theme)
    missing = [name for name, key in (("AboutYouTube", "hover_red"),
                                      ("AboutContact", "hover_yellow"),
                                      ("AboutUpdate", "hover_green"))
               if f"QPushButton#{name}:hover" not in css or colors[key] not in css]
    report(f"[{theme}] 세 단추에 각각 레드·노랑·그린 호버가 걸려 있다", not missing, f"{missing}")

print()
print("=== 2. 확인 결과를 반드시 알린다 ===")

seen, _, check = run_check({"tag_name": "v3.3.0", "html_url": "u", "assets": []})
report("이미 최신이어도 알린다", [k for k, _ in seen] == ["notify"],
       f"{seen} — 조용히 지나가면 눌렀는데 아무 일도 안 한 것으로 보인다")
report("확인 뒤 단추가 원래 글로 돌아온다", check.text() == AboutDialog.CHECK_LABEL)

seen, _, _ = run_check(None)
report("확인에 실패해도 알린다", [k for k, _ in seen] == ["notify"], f"{seen}")

seen, _, _ = run_check({"tag_name": "v9.9.9", "html_url": "u", "assets": []})
report("새 버전이 있으면 안내창으로 넘어간다", [k for k, _ in seen] == ["confirm"], f"{seen}")

print()
print("=== 3. 정보 창에서 온 안내는 단추가 하나 ===")

import src.message as message

saved_single = updater.confirm_single
picked = {}


def spy_single(parent, title, text, *, ok_text, **kwargs):
    picked["ok_text"] = ok_text
    return False


updater.confirm_single = spy_single
saved_supported = self_update.supported
self_update.supported = lambda: True
"""소스로 돌리면 supported()가 False라 교체 경로에 닿지 못한다.

빌드된 실행본에서만 자동 업데이트가 돌기 때문인데, 검사에서 보려는 것은 그
분기가 아니라 단추 구성이라 참으로 만들어 지나가게 한다.
"""
try:
    updater.prompt_and_update(None, {"tag_name": "v9.9.9", "html_url": "u",
                                     "assets": [{"name": "a.zip",
                                                 "browser_download_url": "u"}]},
                              lambda *a: None, single_button=True)
finally:
    updater.confirm_single = saved_single
    self_update.supported = saved_supported
report("자동 업데이트 단추 하나로 묻는다", picked.get("ok_text") == "자동 업데이트",
       f"{picked} — 이미 확인을 눌러 들어온 자리라 '나중에'가 군더더기다")

report("Esc·X를 단추 누름으로 바꾸지 않는다",
       message._ClosableBox.keyPressEvent is not message.QMessageBox.keyPressEvent
       and message._ClosableBox.closeEvent is not message.QMessageBox.closeEvent,
       "단추가 하나뿐이면 Qt가 그것을 Esc 단추로 삼아, 닫기만 해도 업데이트가 시작된다")

print("ALL PASS" if all(results) else f"SOME FAILED ({results.count(False)}건)")
sys.exit(0 if all(results) else 1)
