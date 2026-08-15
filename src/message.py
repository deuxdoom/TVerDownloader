"""앱 팔레트를 따르는 확인 대화상자.

QMessageBox.question() 같은 정적 함수는 버튼 문구를 바꿀 수 없어 Yes/No가 그대로
나오고, 아이콘도 OS 기본 물음표라 나머지 UI와 겉돈다. 직접 구성해서 문구와
아이콘을 앱 것으로 맞춘다.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMessageBox, QWidget

from src.icons import get_icon
from src.qss import palette

ICON_PX = 40


def confirm(parent: QWidget | None, title: str, text: str, *,
            icon_name: str = "info", color_key: str = "accent",
            theme: str = "light", yes_text: str = "예", no_text: str = "아니오",
            default_yes: bool = False) -> bool:
    """예/아니오 확인 창을 띄우고 '예'를 눌렀는지 돌려준다.

    icon_name은 src/icons_data.py에 임베드된 Fluent 아이콘 이름이다.
    color_key로 강조 색을 고른다(삭제류는 "danger").
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)

    colors = palette(theme)
    icon = get_icon(icon_name, colors.get(color_key, colors["accent"]), ICON_PX)
    if not icon.isNull():
        box.setIconPixmap(icon.pixmap(QSize(ICON_PX, ICON_PX)))

    yes_button = box.addButton(yes_text, QMessageBox.ButtonRole.YesRole)
    no_button = box.addButton(no_text, QMessageBox.ButtonRole.NoRole)
    yes_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(yes_button if default_yes else no_button)

    box.exec()
    return box.clickedButton() is yes_button
