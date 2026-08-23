"""앱 팔레트를 따르는 확인 대화상자.

QMessageBox.question() 같은 정적 함수는 단추 문구를 바꿀 수 없고 아이콘도 OS 기본이라
나머지 UI와 겉돈다. 직접 구성해서 문구와 아이콘을 앱 것으로 맞춘다.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QDialogButtonBox, QGridLayout, QMessageBox, QWidget

from src.icons import get_icon
from src.qss import palette

ICON_PX = 40


class _ConfirmBox(QMessageBox):
    """버튼 줄을 본문과 같은 칸에 놓아 가운데 기준을 하나로 맞춘 확인 창.

    QMessageBox는 본문을 아이콘 오른쪽 칸에 두면서 버튼 줄만 격자 전체에 걸쳐 놓아,
    QSS의 centerButtons가 아이콘 폭의 절반만큼 어긋난다.
    """

    def showEvent(self, event):
        """격자를 다시 짜는 일이 다 끝난 뒤에 자리를 옮긴다.

        QMessageBox는 문구·아이콘·버튼이 바뀔 때마다 격자를 새로 짜서, 구성 도중에
        옮겨 두면 그 다음 setter 한 번에 되돌아간다.
        """
        super().showEvent(event)
        self._align_buttons_to_text()

    def _align_buttons_to_text(self):
        """버튼 줄을 본문이 놓인 마지막 칸으로 옮긴다.

        아이콘이 없으면 버튼 줄이 이미 그 칸에만 있어 손대지 않는다.
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

    icon_name은 src/icons_data.py에 임베드된 Fluent 아이콘 이름이다(삭제류는 "danger").
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

    QMessageBox.information()을 쓰지 않는 이유는 확인 창과 같다 - 나란히 놓으면 다른 앱처럼 보인다.
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


class _ClosableBox(_ConfirmBox):
    """Esc와 X를 단추 누름이 아니라 **창 닫기**로 처리하는 확인 창.

    Qt는 Esc 단추를 정해 두지 않으면 Reject·No 역할을 가진 단추를 그 자리에 앉혀, X로
    닫기만 해도 누른 것이 된다. 그렇다고 그 역할을 아무 데도 주지 않으면 **Qt가 X를 잠가
    버린다.** 답은 Esc와 X를 곧장 reject()로 보내 clickedButton을 None으로 남기는 것이다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False

    def arm_escape(self):
        """Qt에게 '닫는 길이 있다'고 알려 준다. 단추를 다 붙인 뒤에 부른다.

        **재정의만으로는 X가 켜지지 않는다** - Qt는 Esc 단추를 찾지 못하면 제목 표시줄의
        X를 아예 잠근다(실측: SC_CLOSE가 GRAYED). 그래서 보이지 않는 RejectRole 단추를
        하나 두고 그것을 지정한다. 보이는 단추를 쓰면 놓쳤을 때 '지금 업데이트'가 눌린다.
        """
        button = self.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
        button.hide()
        self.setEscapeButton(button)

    def reject(self):
        self._closing = True
        super().reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        event.accept()
        self.reject()


class _LinkBox(_ClosableBox):
    """링크 단추가 창을 닫지 않는 확인 창.

    '내역 확인'은 결정이 아니라 읽어 보는 단추라, 닫히면 보고 나서 받을 방법이 사라진다.
    **닫기와 반드시 갈라야 한다** - clickedButton은 한 번 눌리면 남아 있어서, 링크를 누른
    뒤 Esc를 치면 done()이 또 '링크를 눌렀다'로 읽어 브라우저가 열리고 창이 갇힌다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_button = None
        self._on_link = None

    def set_link(self, button, handler):
        self._link_button = button
        self._on_link = handler

    def done(self, result):
        if not self._closing and self._link_button is not None \
                and self.clickedButton() is self._link_button:
            if self._on_link is not None:
                self._on_link()
            return
        super().done(result)


def confirm_single(parent: QWidget | None, title: str, text: str, *, ok_text: str,
                   icon_name: str = "info", color_key: str = "accent",
                   theme: str = "light") -> bool:
    """단추 하나짜리 확인 창. 그 단추를 눌렀는지 돌려준다.

    notify()와 달리 결과를 돌려주고, confirm()과 달리 거절 단추가 없다. 그만두려면 창을 닫는다.
    """
    box = _ClosableBox(parent)
    box.setWindowTitle(title)
    box.setText(text)

    colors = palette(theme)
    icon = get_icon(icon_name, colors.get(color_key, colors["accent"]), ICON_PX)
    if not icon.isNull():
        box.setIconPixmap(icon.pixmap(QSize(ICON_PX, ICON_PX)))

    ok_button = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    ok_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(ok_button)
    box.arm_escape()

    box.exec()
    return box.clickedButton() is ok_button


def confirm_with_link(parent: QWidget | None, title: str, text: str, *,
                      yes_text: str, link_text: str, on_link,
                      icon_name: str = "info", color_key: str = "accent",
                      theme: str = "light") -> bool:
    """'실행'과 '링크 열기' 두 단추를 둔 확인 창. 실행을 눌렀는지 돌려준다.

    **링크 단추는 창을 닫지 않는다**(_LinkBox). **confirm()을 쓰지 않는 것은 창을 닫은 것과
    링크를 누른 것을 갈라야 하기 때문이다** - '아니오'가 NoRole이면 Qt가 그것을 Esc 단추로
    앉혀, X로 닫기만 해도 브라우저가 열린다(Accept/Action 조합이면 None으로 남는다).
    """
    box = _LinkBox(parent)
    box.setWindowTitle(title)
    box.setText(text)

    colors = palette(theme)
    icon = get_icon(icon_name, colors.get(color_key, colors["accent"]), ICON_PX)
    if not icon.isNull():
        box.setIconPixmap(icon.pixmap(QSize(ICON_PX, ICON_PX)))

    yes_button = box.addButton(yes_text, QMessageBox.ButtonRole.AcceptRole)
    link_button = box.addButton(link_text, QMessageBox.ButtonRole.ActionRole)
    yes_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(yes_button)
    box.set_link(link_button, on_link)
    box.arm_escape()

    box.exec()
    return box.clickedButton() is yes_button
