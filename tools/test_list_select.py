import sys

from PyQt6.QtCore import QEventLoop, QRect, QSize, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QListWidgetItem

app = QApplication(sys.argv)
app.setStyle("Fusion")

import _bootstrap
_bootstrap.setup()

import TVerDownloader as T
from src.qss import build_qss, palette, blend
from src.ui.main_window_ui import MainWindowUI
from src.widgets import DownloadItemWidget, HistoryItemWidget, FavoriteItemWidget

T.setup_app_font(app)
OUT = _bootstrap.OUT_DIR
results = []

OUTSIDE = 1
INSIDE = 6
"""카드 **우상단** 모서리에서 대각선으로 잰 거리(논리 픽셀).

반지름 10짜리 둥근 모서리를 실측해 고른 값이다. 대각선을 따라가면 k=0~1은 목록
배경, k=3이 카드 테두리, k=4부터 카드 배경이었다. 그래서 1은 '카드 바깥',
6은 '확실히 카드 안'이다.

**좌상단이 아니라 우상단을 본다.** 왼쪽에는 상태 색 띠(`BroadcastStrip`)가 세로로
붙어 있어 그 색을 사각 자국으로 착각한다.
"""

MUST_BE_CURRENT = True
"""행을 고를 때 current까지 세워야 증상이 나온다.

`setSelected(True)`만으로는 초점 사각형이 그려지지 않아 멀쩡해 보인다. 사람이
마우스로 누르면 selected와 current가 함께 서므로 검사도 그렇게 맞춰야 한다.
이걸 빠뜨린 첫 판에서는 고치기 전 코드에서도 검사가 통과했다.
"""


def report(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def settle(n=8):
    for _ in range(n):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)


def build(theme):
    app.setStyleSheet(build_qss(theme))
    window = QMainWindow()
    ui = MainWindowUI(window)
    ui.setup_ui()
    ui.apply_theme(theme)
    window.resize(1280, 820)
    window.show()
    settle()
    window.grab()
    settle()
    return window, ui


def fill(ui, kind, theme):
    if kind == "DownloadList":
        lst = ui.download_list
    elif kind == "HistoryList":
        lst = ui.history_list
    else:
        lst = ui.fav_list
    for i in range(2):
        item = QListWidgetItem()
        if kind == "DownloadList":
            card = DownloadItemWidget(f"u{i}", theme)
            card.update_progress({"title": "テスト・高", "status": "완료", "percent": 100})
            item.setSizeHint(card.sizeHint())
        elif kind == "HistoryList":
            card = HistoryItemWidget(f"u{i}", {"title": "テスト・高",
                                               "date": "2026-08-16"}, theme)
            item.setSizeHint(card.sizeHint())
        else:
            card = FavoriteItemWidget(f"https://tver.jp/series/sr{i}",
                                      {"title": "テスト・高"}, theme)
            item.setSizeHint(QSize(lst.column_width(), FavoriteItemWidget.CARD_HEIGHT))
        lst.addItem(item)
        lst.setItemWidget(item, card)
    settle()
    lst.item(0).setSelected(True)
    lst.itemWidget(lst.item(0)).set_selected(True)
    if MUST_BE_CURRENT:
        lst.setCurrentItem(lst.item(0))
    lst.setFocus()
    settle()
    return lst


TINTS = {"DownloadList": "ctx_download", "HistoryList": "ctx_history",
         "FavoritesList": "ctx_favorites"}
TABS = {"DownloadList": 0, "HistoryList": 1, "FavoritesList": 2}

print("=== 고른 행의 둥근 모서리 밖에 사각 자국이 없다 ===")

for theme in ("light", "dark"):
    colors = palette(theme)
    for kind in ("DownloadList", "HistoryList", "FavoritesList"):
        window, ui = build(theme)
        ui.tabs.setCurrentIndex(TABS[kind])
        settle()
        lst = fill(ui, kind, theme)
        window.activateWindow()
        settle()

        shot = lst.viewport().grab()
        d = shot.devicePixelRatio()
        img = shot.toImage()
        card = lst.itemWidget(lst.item(0)).geometry()
        tint = blend(colors[TINTS[kind]], colors["surface"], 0.18).upper()
        list_bg = colors["bg"].upper()

        def at(lx, ly):
            c = img.pixelColor(int(lx * d), int(ly * d))
            return "#{:02X}{:02X}{:02X}".format(c.red(), c.green(), c.blue())

        corner = at(card.right() - OUTSIDE, card.top() + OUTSIDE)
        inside = at(card.right() - INSIDE, card.top() + INSIDE)

        crop = QRect(int((card.right() - 27) * d), int((card.top() - 6) * d),
                     int(34 * d), int(34 * d))
        shot.copy(crop).scaled(crop.width() * 8, crop.height() * 8,
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.FastTransformation).save(
            f"{OUT}/select_{kind}_{theme}.png")

        fits = card.right() < lst.viewport().width()
        report(f"[{theme}/{kind}] 카드 오른쪽 끝이 화면 안에 있다(검사 전제)", fits,
               f"카드={card} 뷰포트폭={lst.viewport().width()}")
        report(f"[{theme}/{kind}] 모서리 밖은 목록 배경 그대로", corner == list_bg,
               f"모서리={corner} 기대={list_bg} (초점 사각형이 그려지면 회색이 섞인다)")
        report(f"[{theme}/{kind}] 카드 안쪽은 강조색으로 칠해진다", inside == tint,
               f"안쪽={inside} 기대={tint}")

        window.close()
        window.deleteLater()
        settle()

print()
print(f"결과 PNG: {OUT}")
print(f"{sum(results)}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
