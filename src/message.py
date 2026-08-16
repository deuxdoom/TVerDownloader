"""앱 팔레트를 따르는 확인 대화상자.

QMessageBox.question() 같은 정적 함수는 버튼 문구를 바꿀 수 없어 Yes/No가 그대로
나오고, 아이콘도 OS 기본 물음표라 나머지 UI와 겉돈다. 직접 구성해서 문구와
아이콘을 앱 것으로 맞춘다.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
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


class _ClosableBox(_ConfirmBox):
    """Esc와 X를 단추 누름이 아니라 **창 닫기**로 처리하는 확인 창.

    QMessageBox는 Esc 단추를 따로 정해 두지 않으면 Reject·No 역할을 가진 단추를
    그 자리에 앉힌다. 단추 하나짜리 창이면 그 하나가 뽑혀, X로 닫기만 해도 누른
    것이 된다. 앱을 껐다 켜는 동작이 걸려 있으면 그냥 둘 수 없다.

    그렇다고 Reject·No 역할을 아무 데도 주지 않으면 **Qt가 X를 비활성으로 만들고
    Esc도 먹지 않는다.** 닫는 뜻을 알 수 없어서다. 실제로 그렇게 만들었다가 창이
    갇혔다.

    답은 역할을 비우는 것이 아니라 닫는 길을 직접 내주는 것이다. Esc와 X를 곧장
    reject()로 보내면 창은 정상으로 닫히고, clickedButton은 None으로 남아 눌린
    것과 구별된다. _closing은 그 닫힘이 사용자가 낸 것임을 done()에 알린다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False

    def arm_escape(self):
        """Qt에게 '닫는 길이 있다'고 알려 준다. 단추를 다 붙인 뒤에 부른다.

        **재정의만으로는 X가 켜지지 않는다.** Qt는 Esc 단추를 찾지 못하면 제목
        표시줄의 X를 아예 잠가 버린다(실측: 시스템 메뉴의 SC_CLOSE가 GRAYED).
        동작은 closeEvent 재정의로 고칠 수 있어도, 잠긴 X는 눌리지조차 않는다.

        그래서 보이지 않는 '닫기'를 하나 두고 그것을 Esc 단추로 지정한다. 실제로
        눌릴 일은 없다 — Esc와 X는 위의 재정의가 먼저 가로채 reject()로 보낸다.
        이건 Qt에게 보여 주는 표지이자, **재정의가 어느 경로를 놓쳤을 때의 대비**다.
        그때 눌리더라도 아무 동작 없이 창만 닫힌다(RejectRole).

        지정 대상으로 보이는 단추를 쓰면 안 된다. 놓쳤을 때 '지금 업데이트'가
        눌려 앱이 꺼졌다 켜지는 쪽으로 새는데, 그건 실패 방향이 가장 나쁘다.
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

    '내역 확인'은 결정이 아니라 **읽어 보는** 단추다. 눌러서 창이 닫히면 내용을
    본 뒤 곧바로 받을 방법이 사라져, 프로그램을 다시 켜야 한다. 무엇이 바뀌었는지
    보고 나서 받을지 정하는 것이 이 단추의 본래 쓸모다.

    QMessageBox는 어느 단추를 눌러도 done()으로 창을 닫는다. 그 단추일 때만
    삼켜서 창을 남긴다.

    **닫기와 반드시 갈라야 한다.** clickedButton은 한 번 눌리면 그대로 남아 있어서,
    링크를 누른 뒤 Esc를 치면 done()이 또 '링크를 눌렀다'로 읽는다. 그러면 브라우저가
    한 번 더 열리고 창은 닫히지 않아 **갇힌다.** _closing(_ClosableBox)이 그 닫힘이
    사용자가 낸 것임을 알려 주므로 그때는 그냥 보낸다.
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

    notify()와 다른 점은 **결과를 돌려준다**는 것이고, confirm()과 다른 점은 거절
    단추가 없다는 것이다. 이미 하겠다고 눌러서 들어온 자리라 '나중에'가 군더더기일
    때 쓴다. 그만두려면 창을 닫으면 된다(_ClosableBox).
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

    **링크 단추는 창을 닫지 않는다**(_LinkBox). 내용을 보고 돌아와 그대로 실행을
    누를 수 있어야 하기 때문이다. 그만두려면 창을 닫으면 된다.

    **창을 닫은 것과 링크를 누른 것을 반드시 가려야 해서 confirm()을 쓰지 않는다.**
    confirm()의 '아니오'는 NoRole인데, Qt는 Esc 단추를 따로 정해 두지 않으면
    Reject·No 역할을 가진 단추를 그 자리에 앉힌다. 그래서 X나 Esc로 닫아도 그
    단추를 누른 것으로 돌아온다. 링크 단추에 그대로 쓰면 **창을 닫기만 해도
    브라우저가 열린다.**

    실측으로 가른 결과는 이렇다.

    | 두 단추의 역할 | Esc·X를 눌렀을 때 clickedButton |
    |---|---|
    | Yes / No | **두 번째 단추** (구별 불가) |
    | Accept / Action | None (구별됨) |

    다만 Reject·No를 아무 데도 주지 않으면 Qt가 **X를 비활성으로 만들고 Esc도
    먹지 않는다.** 그래서 역할을 비우는 것으로 끝내지 않고 닫는 길을 직접
    내준다(_ClosableBox).
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
