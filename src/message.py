"""앱 팔레트를 따르는 확인 대화상자.

QMessageBox.question() 같은 정적 함수는 버튼 문구를 바꿀 수 없어 Yes/No가 그대로
나오고, 아이콘도 OS 기본 물음표라 나머지 UI와 겉돈다. 직접 구성해서 문구와
아이콘을 앱 것으로 맞춘다.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QDialogButtonBox, QGridLayout, QMessageBox, QWidget

from src.icons import get_icon
from src.qss import palette

ICON_PX = 40


class _ConfirmBox(QMessageBox):
    """버튼 줄을 본문과 같은 칸에 놓아 가운데 기준을 하나로 맞춘 확인 창.

    QMessageBox는 본문을 아이콘 오른쪽 칸에 두면서 버튼 줄만 격자 전체(아이콘 칸
    포함)에 걸쳐 놓는다. QSS의 centerButtons는 그 걸쳐진 폭을 기준으로 삼으므로,
    가운데 정렬한 본문과 아이콘 폭의 절반만큼 어긋나 보인다. 버튼 줄을 본문 칸으로
    옮기면 두 기준이 같아진다.
    """

    def showEvent(self, event):
        """격자를 다시 짜는 일이 다 끝난 뒤에 자리를 옮긴다.

        QMessageBox는 문구·아이콘·버튼이 바뀔 때마다 격자를 통째로 새로 만든다.
        구성하는 도중에 옮겨 두면 그 다음 setter 한 번에 되돌아가므로, 창을 띄우는
        시점까지 미룬다.
        """
        super().showEvent(event)
        self._align_buttons_to_text()

    def _align_buttons_to_text(self):
        """버튼 줄을 본문이 놓인 마지막 칸으로 옮긴다.

        본문은 아이콘이 있으면 셋째 칸, 없으면 첫 칸에 놓이는데 어느 쪽이든 격자의
        마지막 칸이다. 아이콘이 없을 때는 버튼 줄이 이미 그 칸에만 있어서 옮길
        것이 없고, 그대로 두어야 띄울 때마다 배치를 다시 계산하지 않는다.
        """
        grid = self.layout()
        buttons = self.findChild(QDialogButtonBox)
        if not isinstance(grid, QGridLayout) or buttons is None:
            return
        row, column, _, span = grid.getItemPosition(grid.indexOf(buttons))
        text_column = grid.columnCount() - 1
        if column == text_column and span == 1:
            return
        grid.removeWidget(buttons)
        grid.addWidget(buttons, row, text_column, 1, 1)


def _build_box(parent: QWidget | None, title: str, text: str,
               icon_name: str, color_key: str, theme: str) -> _ConfirmBox:
    """제목·문구·아이콘까지 채운 상자를 만든다. 단추는 부르는 쪽이 붙인다.

    icon_name은 src/icons_data.py에 임베드된 Fluent 아이콘 이름이다.
    color_key로 강조 색을 고른다(삭제류는 "danger").
    """
    box = _ConfirmBox(parent)
    box.setWindowTitle(title)
    box.setText(text)

    colors = palette(theme)
    icon = get_icon(icon_name, colors.get(color_key, colors["accent"]), ICON_PX)
    if not icon.isNull():
        box.setIconPixmap(icon.pixmap(QSize(ICON_PX, ICON_PX)))
    return box


def notify(parent: QWidget | None, title: str, text: str, *,
           icon_name: str = "info", color_key: str = "accent",
           theme: str = "light", ok_text: str = "확인") -> None:
    """단추 하나짜리 알림 창.

    QMessageBox.information()을 쓰지 않는 이유는 확인 창과 같다. 아이콘이 OS 기본
    것이고 단추 문구를 바꿀 수 없어, 나란히 놓으면 두 창이 다른 앱처럼 보인다.
    """
    box = _build_box(parent, title, text, icon_name, color_key, theme)
    ok_button = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    ok_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(ok_button)
    box.exec()


def confirm(parent: QWidget | None, title: str, text: str, *,
            icon_name: str = "info", color_key: str = "accent",
            theme: str = "light", yes_text: str = "예", no_text: str = "아니오",
            default_yes: bool = False) -> bool:
    """예/아니오 확인 창을 띄우고 '예'를 눌렀는지 돌려준다."""
    box = _build_box(parent, title, text, icon_name, color_key, theme)

    yes_button = box.addButton(yes_text, QMessageBox.ButtonRole.YesRole)
    no_button = box.addButton(no_text, QMessageBox.ButtonRole.NoRole)
    yes_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(yes_button if default_yes else no_button)

    box.exec()
    return box.clickedButton() is yes_button
