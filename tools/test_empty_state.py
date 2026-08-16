import sys

from PyQt6.QtCore import QEventLoop, QSize, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QListWidgetItem

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src.qss import build_qss, palette
from src.ui.main_window_ui import MainWindowUI

T.setup_app_font(app)
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


def build(theme):
    """진짜 MainWindow는 생성자에서 준비 스레드를 띄운다. 보려는 것은 목록 위에
    얹힌 안내뿐이라 UI 조립만 그대로 빌려 온다."""
    app.setStyleSheet(build_qss(theme))
    window = QMainWindow()
    ui = MainWindowUI(window)
    ui.setup_ui()
    ui.apply_theme(theme)
    window.resize(1100, 700)
    window.show()
    settle()
    return window, ui


def teardown(*windows):
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


def shown(overlay) -> bool:
    """안내가 스스로를 내놓은 상태인지.

    isVisible()은 안 된다. 다른 탭에 있는 목록은 탭을 고르기 전까지 조상이
    숨어 있어, 안내가 제대로 서 있어도 False가 나온다. 여기서 보려는 것은
    '항목 수에 맞게 결정했는가'다. 실제로 화면에 뜨는지는 6절에서 탭을 열어
    따로 확인한다.
    """
    return not overlay.isHidden()


def add_row(list_widget):
    item = QListWidgetItem("x")
    item.setSizeHint(QSize(100, 40))
    list_widget.addItem(item)


window, ui = build("light")
LISTS = (("다운로드", ui.download_list, ui.download_empty),
         ("기록", ui.history_list, ui.history_empty),
         ("즐겨찾기", ui.fav_list, ui.fav_empty))

print("=== 1. 비었을 때만 보인다 ===")

for label, list_widget, overlay in LISTS:
    report(f"[{label}] 처음에는 안내가 보인다", shown(overlay),
           f"제목={overlay.title_label.text()!r}")

for label, list_widget, overlay in LISTS:
    add_row(list_widget)
    settle()
    gone = not shown(overlay)
    list_widget.clear()
    settle()
    back = shown(overlay)
    report(f"[{label}] 항목을 넣으면 사라지고 지우면 돌아온다", gone and back,
           f"넣은 뒤 숨김={gone} 지운 뒤 보임={back}")

for label, list_widget, overlay in LISTS:
    add_row(list_widget)
    add_row(list_widget)
    settle()
    list_widget.takeItem(0)
    settle()
    still_hidden = not shown(overlay)
    list_widget.takeItem(0)
    settle()
    report(f"[{label}] 마지막 한 줄을 뺄 때 돌아온다",
           still_hidden and shown(overlay))


print()
print("=== 2. 목록을 덮되 가로막지는 않는다 ===")

for label, list_widget, overlay in LISTS:
    covers = overlay.geometry() == list_widget.viewport().rect()
    report(f"[{label}] 뷰포트를 그대로 덮는다", covers,
           f"안내={overlay.geometry()} 뷰포트={list_widget.viewport().rect()}")

for label, list_widget, overlay in LISTS:
    passes = overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    report(f"[{label}] 마우스를 통과시킨다(우클릭·끌어놓기)", passes)

before = ui.download_empty.geometry()
window.resize(1280, 820)
settle()
report("창 크기를 바꾸면 따라 늘어난다",
       ui.download_empty.geometry() == ui.download_list.viewport().rect()
       and ui.download_empty.geometry() != before,
       f"{before} -> {ui.download_empty.geometry()}")


print()
print("=== 3. 글이 상자 안에 온전히 들어간다 ===")


def text_fits(overlay) -> bool:
    """접힌 설명 줄이 잘리지 않았는지.

    QLabel은 wordWrap을 켜도 한 줄 높이만 요구해서, 두 줄짜리 글이 겹쳐
    그려진 채로도 다른 검사는 모두 통과한다. 실제로 필요한 높이와 받은
    높이를 직접 견줘야 걸린다.
    """
    label = overlay.description_label
    return label.height() >= label.heightForWidth(label.width())


for label, list_widget, overlay in LISTS:
    desc = overlay.description_label
    report(f"[{label}] 설명 줄이 잘리지 않는다", text_fits(overlay),
           f"폭={desc.width()} 높이={desc.height()} "
           f"필요={desc.heightForWidth(desc.width())}")
    report(f"[{label}] 설명 줄이 목록 밖으로 넘치지 않는다",
           desc.width() <= list_widget.viewport().width(),
           f"글 {desc.width()} <= 목록 {list_widget.viewport().width()}")

window.resize(MainWindowUI.MIN_WIDTH_WITH_LOG, MainWindowUI.MIN_HEIGHT)
settle()
for label, list_widget, overlay in LISTS:
    desc = overlay.description_label
    report(f"[{label}] 최소 폭 창에서도 잘리거나 넘치지 않는다",
           text_fits(overlay) and desc.width() <= list_widget.viewport().width(),
           f"글 {desc.width()}x{desc.height()} 목록 {list_widget.viewport().width()}")
window.resize(1280, 820)
settle()

ui.history_empty.set_filtered(True)
settle()
report("문구를 바꾼 뒤에도 높이가 다시 맞는다", text_fits(ui.history_empty),
       f"{ui.history_empty.description_label.text()!r}")
ui.history_empty.set_filtered(False)


print()
print("=== 4. 검색으로 빈 것은 다르게 말한다 ===")

for label, overlay in (("기록", ui.history_empty), ("즐겨찾기", ui.fav_empty)):
    plain = overlay.title_label.text()
    overlay.set_filtered(True)
    searched = overlay.title_label.text()
    overlay.set_filtered(False)
    report(f"[{label}] 검색 결과가 없을 때 문구가 바뀐다",
           plain != searched and "찾" in searched,
           f"{plain!r} -> {searched!r}")

report("다운로드는 검색이 없어 문구가 하나뿐이다",
       ui.download_empty._messages[True] == ui.download_empty._messages[False])


print()
print("=== 5. 테마를 따라간다 ===")

light_icon = ui.download_empty.icon_label.pixmap().toImage()
ui.apply_theme("dark")
app.setStyleSheet(build_qss("dark"))
settle()
dark_icon = ui.download_empty.icon_label.pixmap().toImage()
report("테마를 바꾸면 아이콘 색이 바뀐다", light_icon != dark_icon)
report("아이콘이 비어 있지 않다",
       not ui.download_empty.icon_label.pixmap().isNull(),
       f"크기={ui.download_empty.icon_label.pixmap().size()}")

dim = {t: palette(t)["text_dim"] for t in ("light", "dark")}
report("두 테마의 흐린 글자색이 서로 다르다", dim["light"] != dim["dark"], str(dim))
ui.apply_theme("light")
app.setStyleSheet(build_qss("light"))
settle()


print()
print("=== 6. 탭 툴팁 ===")

for index, (_icon, _ctx, tooltip) in enumerate(MainWindowUI.TAB_ICONS):
    got = ui.tabs.tabToolTip(index)
    report(f"[{ui.tabs.tabText(index)}] 툴팁이 붙어 있다",
           got == tooltip and 0 < len(got) <= 14, f"{got!r} ({len(got)}자)")


print()
print("=== 7. 렌더 ===")

for theme in ("light", "dark"):
    shot_window, shot_ui = build(theme)
    overlays = (shot_ui.download_empty, shot_ui.history_empty, shot_ui.fav_empty)
    for index in range(3):
        shot_ui.tabs.setCurrentIndex(index)
        settle()
        name = ("download", "history", "favorites")[index]
        shot_window.grab().save(f"{OUT}/empty_{name}_{theme}.png")
        overlay = overlays[index]
        viewport = (shot_ui.download_list, shot_ui.history_list,
                    shot_ui.fav_list)[index].viewport()
        report(f"[{theme}] 탭을 열면 제자리에 실제로 뜬다 ({name})",
               overlay.isVisible() and overlay.geometry() == viewport.rect(),
               f"보임={overlay.isVisible()} 안내={overlay.geometry()} "
               f"뷰포트={viewport.rect()}")
    teardown(shot_window)

teardown(window)
print(f"결과 PNG: {OUT}")
print(f"{sum(results)}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
