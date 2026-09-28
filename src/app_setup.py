"""앱 전역에 거는 Qt 준비 - 번들 서체와 렌더링 규칙, 팝업의 아이콘 색과 모양, Qt 기본 위젯 번역.

메인 창과 업데이트 적용 창(`--apply-update`)이 같은 준비를 거치도록 prepare_app() 한 곳에서 부른다.
**서체 렌더링 조합은 바꾸지 않는다**(CLAUDE.md 3절) - QSS가 폰트를 새로 만들면 FontRenderingGuard가 다시 입힌다.
"""
from pathlib import Path
from typing import List

from PyQt6.QtCore import QEvent, QLibraryInfo, QObject, QTranslator
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QComboBox, QMenu, QWidget

from src import i18n
from src.icons import is_monochrome_white, tint_icon
from src.qss import build_qss, palette, UI_FONT_FALLBACKS
from src.qtparts import (apply_popup_shape, apply_combo_popup_shape,
                         flatten_combo_popup_margins, COMBO_POPUP_OBJECT)
from src.utils import get_resource_path, localized_app_name
from versioninfo import APP_VERSION

FONT_DIR = Path("assets") / "fonts"
UI_FONT_FILES = [
    FONT_DIR / "PretendardVariable.ttf",
    FONT_DIR / "PretendardJP-Regular.ttf",
]
MONO_FONT_FILES = [FONT_DIR / "JetBrainsMono-Regular.ttf"]

UI_FONT_HINTING = QFont.HintingPreference.PreferNoHinting
UI_FONT_STYLE_STRATEGY = QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality

_app_filters: List[QObject] = []
_menu_icon_tinter: "MenuIconTinter | None" = None
_qt_translator: QTranslator | None = None
"""앱에 건 전역 필터와 Qt 번역을 붙잡아 둔다. 메뉴 색을 바꾸거나 번역을 갈아 끼울 때 다시 찾는다.

앱 객체에 파이썬 속성으로 달아 두면 QApplication 타입에 없는 속성이라 편집기가 오류로 긋는다.
"""


class FontRenderingGuard(QObject):
    """스타일시트가 새로 만든 폰트에 글자 렌더링 설정을 다시 입힌다.

    QSS에 font 속성이 있으면 Qt가 QFont를 새로 만들고 setFont()의 힌팅·안티앨리어싱이
    따라오지 않는다. 덮이는 시점은 Polish가 아니라 그 뒤의 FontChange라 셋을 모두 본다.
    """

    WATCHED = (QEvent.Type.Polish, QEvent.Type.FontChange, QEvent.Type.StyleChange)

    def eventFilter(self, a0, a1):
        if a1 is not None and a1.type() in self.WATCHED and isinstance(a0, QWidget):
            font = a0.font()
            if (font.hintingPreference() != UI_FONT_HINTING
                    or font.styleStrategy() != UI_FONT_STYLE_STRATEGY):
                font.setHintingPreference(UI_FONT_HINTING)
                font.setStyleStrategy(UI_FONT_STYLE_STRATEGY)
                a0.setFont(font)
        return super().eventFilter(a0, a1)


def register_font(path: Path) -> List[str]:
    """서체 파일 하나를 등록하고 패밀리명 목록을 돌려준다. 실패해도 빈 목록으로 돌아간다."""
    try:
        full_path = get_resource_path(path)
        if not full_path.is_file():
            print(f"INFO: 번들 서체를 찾지 못했습니다: {full_path}")
            return []
        font_id = QFontDatabase.addApplicationFont(str(full_path))
        if font_id == -1:
            print(f"WARNING: 서체를 불러오지 못했습니다: {full_path}")
            return []
        return QFontDatabase.applicationFontFamilies(font_id)
    except Exception as e:
        print(f"WARNING: 서체 등록 중 오류가 발생했습니다: {path} - {e}")
        return []


class MenuIconTinter(QObject):
    """메뉴가 열릴 때 흰색 아이콘을 테마 글자색으로 바꿔 놓는다.

    입력칸 우클릭 메뉴는 Qt가 만들고 아이콘도 Qt 것(:/icons)이라 일곱 개가 전부 흰색이고
    라이트 테마에서 묻힌다. 새로 만들지 않는 것은 항목이 켜지고 꺼지는 조건을 그대로 두려는 것.
    """

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color

    def set_color(self, color: str):
        self._color = color

    def eventFilter(self, a0, a1):
        if a1 is not None and a1.type() == QEvent.Type.Show and isinstance(a0, QMenu):
            self._tint(a0)
        return super().eventFilter(a0, a1)

    def _tint(self, menu):
        """메뉴 항목들의 아이콘을 지금 색으로 맞춘다.

        칠하기 전 원본을 들고 있는다. 한 번 칠하면 더는 흰색이 아니라서, 원본 없이는 테마가
        바뀌었을 때 다시 칠할 대상으로 알아보지 못한다.
        """
        for action in menu.actions():
            icon = action.icon()
            if icon.isNull() or action.property("tinted_for") == self._color:
                continue
            source = action.property("untinted_icon")
            if source is None:
                if not is_monochrome_white(icon):
                    continue
                source = icon
                action.setProperty("untinted_icon", source)
            action.setIcon(tint_icon(source, self._color))
            action.setProperty("tinted_for", self._color)


class PopupShapeGuard(QObject):
    """제 창을 가진 팝업(메뉴·콤보 펼침 목록)을 모두 같은 모양으로 맞춘다.

    한 곳에서 거는 것은 콤보박스가 여러 파일에 흩어져 있고, 입력칸 우클릭 메뉴처럼 클래스를
    고를 수 없는 팝업도 있어서다. Show에서 걸면 Qt가 창을 숨겨 메뉴가 뜨지 않아 Polish에서 건다.
    """

    def eventFilter(self, a0, a1):
        if a1 is None or a0 is None:
            return super().eventFilter(a0, a1)
        if a1.type() == QEvent.Type.Polish:
            if isinstance(a0, QMenu):
                apply_popup_shape(a0)
            elif isinstance(a0, QComboBox):
                apply_combo_popup_shape(a0)
        elif (a1.type() == QEvent.Type.Show
              and a0.objectName() == COMBO_POPUP_OBJECT):
            flatten_combo_popup_margins(a0)
        return super().eventFilter(a0, a1)


def setup_menu_icons(app: QApplication, theme: str) -> MenuIconTinter:
    """팝업 아이콘 색과 모양을 우리 것에 맞추는 감시자를 앱에 건다."""
    global _menu_icon_tinter
    tinter = MenuIconTinter(palette(theme)["text"], app)
    app.installEventFilter(tinter)
    shape = PopupShapeGuard(app)
    app.installEventFilter(shape)
    _menu_icon_tinter = tinter
    _app_filters.extend((tinter, shape))
    return tinter


def set_menu_icon_color(color: str) -> None:
    """테마를 바꿀 때 메뉴 아이콘을 칠할 색을 바꾼다. 감시자를 걸기 전이면 할 일이 없다."""
    if _menu_icon_tinter is not None:
        _menu_icon_tinter.set_color(color)


def setup_translations(app: QApplication) -> None:
    """Qt 기본 위젯의 문구를 **앱이 쓰는 언어**로 맞춘다.

    입력칸 우클릭 메뉴와 QMessageBox 기본 단추가 여기서 나온다. OS 언어가 아니라 i18n이
    정한 언어를 보는 것은, 설정에서 영어를 골랐는데 그 메뉴만 한국어로 남는 것이 이
    프로젝트의 다국어 작업을 시작하게 만든 불일치와 같은 종류이기 때문이다. 싣는 언어는
    spec의 TRANSLATION_LANGS가 정하고, 거기 없는 언어는 아무것도 설치하지 않아 Qt
    기본값인 영어로 나온다. 언어를 바꿀 때 다시 불러도 되도록 앞서 건 번역은 떼어 낸다.
    """
    global _qt_translator
    try:
        previous = _qt_translator
        if previous is not None:
            app.removeTranslator(previous)
            previous.deleteLater()
            _qt_translator = None
        locale = i18n.qt_locale()
        translator = QTranslator(app)
        candidates = [
            str(get_resource_path(Path("translations"))),
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        ]
        for directory in candidates:
            if translator.load(locale, "qtbase", "_", directory):
                app.installTranslator(translator)
                _qt_translator = translator
                return
        print(f"INFO: {locale.name()} 용 Qt 번역을 찾지 못했습니다. 영어로 표시됩니다.")
    except Exception as e:
        print(f"WARNING: Qt 번역을 불러오지 못했습니다: {e}")


def setup_app_font(app: QApplication) -> None:
    """번들 서체를 등록하고 앱 기본 서체를 지정한다. 실패한 것은 시스템 서체로 폴백한다."""
    families: List[str] = []
    for font_file in UI_FONT_FILES:
        registered = register_font(font_file)
        if registered:
            families.append(registered[0])
    for font_file in MONO_FONT_FILES:
        register_font(font_file)

    if not families:
        print("INFO: 번들 서체를 하나도 등록하지 못했습니다. 시스템 서체를 사용합니다.")

    try:
        font = QFont()
        font.setFamilies(families + list(UI_FONT_FALLBACKS))
        font.setHintingPreference(UI_FONT_HINTING)
        if UI_FONT_STYLE_STRATEGY is not None:
            font.setStyleStrategy(UI_FONT_STYLE_STRATEGY)
        app.setFont(font)
        guard = FontRenderingGuard(app)
        app.installEventFilter(guard)
        _app_filters.append(guard)
    except Exception as e:
        print(f"WARNING: 기본 서체 지정에 실패했습니다: {e}. Qt 기본값을 사용합니다.")


def prepare_app(app: QApplication, config: dict) -> str:
    """언어부터 스타일까지 앱 전역 준비를 정해진 차례로 하고 테마 이름을 돌려준다.

    진입점과 업데이트 적용 창이 같은 여덟 줄을 따로 들고 있어 한쪽만 고쳐질 뻔했다. 언어가
    먼저인 것은 뒤의 준비(Qt 번역·앱 이름)가 그 언어를 읽기 때문이다.
    """
    i18n.setup(config)
    theme = config.get("theme", "light")
    setup_menu_icons(app, theme)
    setup_translations(app)
    setup_app_font(app)
    app.setStyleSheet(build_qss(theme))
    app.setApplicationName(localized_app_name())
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    return theme
