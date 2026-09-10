"""앱 팔레트를 따르는 확인 대화상자.

QMessageBox.question() 같은 정적 함수는 단추 문구를 바꿀 수 없고 아이콘도 OS 기본이라
나머지 UI와 겉돈다. 직접 구성해서 문구와 아이콘을 앱 것으로 맞춘다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QMessageBox, QWidget

from src.i18n import t
from src.window_frame import apply_dialog_frame, center_dialog


class _ConfirmBox(QMessageBox):
    """글과 단추 줄을 창 가운데에 세우는 확인 창.

    **아이콘을 제목 줄로 옮긴 뒤에도 QMessageBox는 그 자리를 비워 둔다** - 격자 첫 칸에
    15px짜리 빈칸이 남아(실측) 글과 단추가 창 가운데에서 오른쪽으로 8px 밀린다. 두 줄을
    첫 칸부터 격자 전체에 걸쳐 놓아야 QSS의 AlignCenter·centerButtons가 창을 기준으로
    가운데를 잡는다.
    """

    BODY_MARGINS = (24, 20, 24, 20)
    """본문 상자의 안쪽 여백. QMessageBox 기본값(9px)은 글이 모서리에 붙어 답답하다."""

    BOX_WIDTH = 320
    TEXT_MIN_HEIGHT = 24
    """알림 창 본문이 적어도 차지할 폭과 글 높이(제목 줄과 그림자 여백을 뺀 값).

    **폭은 붙들고 높이는 내용을 따른다.** 잇달아 뜨는 창들이 문구 길이대로 148 · 198 ·
    264px가 되면 같은 프로그램의 창으로 보이지 않고(사용자 지적), 반대로 높이까지 한 값에
    묶으면 한 줄짜리 창에 빈 자리만 남는다(그것도 사용자 지적, 2026-09-09).

    **최소값이지 고정값이 아니라서 언어를 가리지 않는다.** 번역이 길면 그만큼 넓어지고
    짧으면 이 폭에서 멈춘다 - 일곱 언어를 재어 320~372px 안에 들었다.
    """

    def showEvent(self, event):
        """격자를 다시 짜는 일이 다 끝난 뒤에 자리를 옮기고 크기를 맞춘다.

        QMessageBox는 문구·아이콘·버튼이 바뀔 때마다 격자를 새로 짜서, 구성 도중에
        옮겨 두면 그 다음 setter 한 번에 되돌아간다.
        """
        super().showEvent(event)
        self._center_content()
        self._apply_common_size()

    def resizeEvent(self, event):
        """크기가 정해진 뒤에 다시 부모 가운데로 놓는다.

        **QMessageBox는 창이 보이고 나서야 제 내용에 맞춰 크기를 굳힌다**(실측: 종료 확인
        창이 show 시점 215x132에서 340x156이 됐다). 자리를 잡는 일은 그 전에 끝나 있어,
        커진 만큼 절반이 그대로 어긋남이 된다 - 문구가 길고 짧은 데 따라 창마다 다른
        자리에 뜨던 것이 이 때문이다(실측: 같은 부모에서 +53 · +64 · +8px).
        """
        super().resizeEvent(event)
        center_dialog(self)

    def _apply_common_size(self):
        """짧은 알림 창을 공통 크기까지 넓힌다.

        **창이 아니라 본문 글에 최소 크기를 준다.** QMessageBox는 제 내용에 맞춘 크기를
        `setFixedSize`로 굳히고 배치 요청이 올 때마다 다시 굳혀서, 창 쪽에 걸어 둔 최소
        크기는 곧바로 덮인다(실측: 최소 폭 300을 걸어도 창은 148px로 돌아왔다). 글이
        차지할 자리를 넓혀 두면 그 셈에 우리 값이 들어가 창이 그만큼 커진다.
        """
        grid = self._content_grid()
        if grid is None:
            return
        grid.setContentsMargins(*self.BODY_MARGINS)
        label = self.findChild(QLabel, "qt_msgbox_label")
        if label is None:
            return
        left, _top, right, _bottom = self.BODY_MARGINS
        label.setMinimumSize(max(0, self.BOX_WIDTH - left - right), self.TEXT_MIN_HEIGHT)

    def _content_grid(self) -> QGridLayout | None:
        """QMessageBox가 쓰는 격자.

        제목 줄을 붙이며 창을 감싸면 이 격자가 본문 상자 안으로 옮겨져, `self.layout()`은
        껍데기를 담은 세로 배치가 된다. 감싸기 전에는 예전처럼 창에 바로 붙어 있다.
        """
        body = getattr(self, "dialog_body", None)
        layout = body.layout() if body is not None else self.layout()
        return layout if isinstance(layout, QGridLayout) else None

    def _center_content(self):
        """아이콘 자리로 남은 빈칸을 걷어내고, 남은 줄들을 격자 전체 폭에 걸쳐 놓는다.

        위젯이 아닌 항목(빈칸)만 골라 빼므로 글·단추는 그대로 남는다. 이미 다 걸쳐 놓은
        뒤에 다시 불려도 하는 일이 없다 - showEvent는 창을 다시 띄울 때마다 온다.
        """
        grid = self._content_grid()
        if grid is None:
            return
        for index in reversed(range(grid.count())):
            item = grid.itemAt(index)
            if item.widget() is None and item.layout() is None:
                grid.takeAt(index)

        columns = max(1, grid.columnCount())
        moves = []
        for index in range(grid.count()):
            widget = grid.itemAt(index).widget()
            if widget is None:
                continue
            row, column, row_span, column_span = grid.getItemPosition(index)
            if column == 0 and column_span == columns:
                continue
            moves.append((widget, row, row_span))
        for widget, row, row_span in moves:
            grid.removeWidget(widget)
            grid.addWidget(widget, row, 0, row_span, columns)


def _frame(box: QMessageBox, theme: str, icon_name: str, color_key: str):
    """제목 표시줄을 떼고 우리 제목 줄을 붙인다. **단추를 다 붙인 뒤에 부른다.**

    **아이콘은 본문이 아니라 제목 줄에 든다.** 본문 왼쪽에 40px짜리로 세워 두면 제목 줄의
    닫기 X와 같은 그림이 한 창에 둘 서고(종료 확인), 그 칸만큼 창이 옆으로 넓어진다.

    크기 조절 띠는 두지 않는다 - 알림 창은 내용에 맞춰 크기가 정해지고 늘릴 일이 없다.
    """
    apply_dialog_frame(box, theme, resizable=False,
                       icon_name=icon_name, color_key=color_key)


def _build_box(parent: QWidget | None, title: str, text: str, theme: str) -> _ConfirmBox:
    """제목과 문구를 채운 상자를 만든다. 단추와 제목 줄은 부르는 쪽이 붙인다."""
    box = _ConfirmBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    return box


def notify(parent: QWidget | None, title: str, text: str, *,
           icon_name: str = "info", color_key: str = "accent",
           theme: str = "light", ok_text: str | None = None) -> None:
    """단추 하나짜리 알림 창.

    QMessageBox.information()을 쓰지 않는 이유는 확인 창과 같다 - 나란히 놓으면 다른 앱처럼 보인다.
    ok_text 기본값을 매개변수 자리에서 바로 t()로 채우지 않는 것은, 그러면 이 함수를
    처음 정의하는 모듈 로드 시점(아직 i18n.setup() 전)에 언어가 굳어 버리기 때문이다.
    """
    box = _build_box(parent, title, text, theme)
    ok_button = box.addButton(ok_text or t("common.ok"), QMessageBox.ButtonRole.AcceptRole)
    ok_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(ok_button)
    _frame(box, theme, icon_name, color_key)
    box.exec()


def confirm(parent: QWidget | None, title: str, text: str, *,
            icon_name: str = "info", color_key: str = "accent",
            theme: str = "light", yes_text: str | None = None, no_text: str | None = None,
            default_yes: bool = False) -> bool:
    """예/아니오 확인 창을 띄우고 '예'를 눌렀는지 돌려준다."""
    box = _build_box(parent, title, text, theme)

    yes_button = box.addButton(yes_text or t("common.yes"), QMessageBox.ButtonRole.YesRole)
    no_button = box.addButton(no_text or t("common.no"), QMessageBox.ButtonRole.NoRole)
    yes_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(yes_button if default_yes else no_button)

    _frame(box, theme, icon_name, color_key)
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
        button = self.addButton(t("common.close"), QMessageBox.ButtonRole.RejectRole)
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

    ok_button = box.addButton(ok_text or t("common.ok"), QMessageBox.ButtonRole.AcceptRole)
    ok_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(ok_button)
    box.arm_escape()

    _frame(box, theme, icon_name, color_key)
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

    yes_button = box.addButton(yes_text, QMessageBox.ButtonRole.AcceptRole)
    link_button = box.addButton(link_text, QMessageBox.ButtonRole.ActionRole)
    yes_button.setObjectName("DangerButton" if color_key == "danger" else "PrimaryButton")
    box.setDefaultButton(yes_button)
    box.set_link(link_button, on_link)
    box.arm_escape()

    _frame(box, theme, icon_name, color_key)
    box.exec()
    return box.clickedButton() is yes_button
