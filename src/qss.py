from src.indicators import indicator_images

UI_FONT_BUNDLED = ("Pretendard Variable", "Pretendard JP")
"""assets/fonts에서 등록하는 번들 서체의 패밀리명."""

UI_FONT_FALLBACKS = ("Yu Gothic UI", "Malgun Gothic", "Segoe UI")
"""번들 등록이 실패해도 글자가 읽히도록 남겨 두는 시스템 서체."""

UI_FONT_FAMILIES = UI_FONT_BUNDLED + UI_FONT_FALLBACKS
"""본문 서체 스택. QApplication.setFont()와 같은 순서를 유지한다.

setFont()로 지정한 폴백 목록은 위젯이 polish될 때 한 개로 뭉개진다. 그러면
Pretendard JP가 빠져 일본어 한자가 맑은 고딕으로 그려진다. QListWidget처럼
항목을 델리게이트가 직접 그리는 위젯에서 특히 눈에 띈다. QSS에 이름을 적어 두면
polish 이후에도 스택이 그대로 남는다.
"""

UI_FONT_STACK = ", ".join(f'"{name}"' for name in UI_FONT_FAMILIES)

SCROLLBAR_WIDTH = 10
"""스크롤바 두께. 목록의 칸 폭 계산이 이 값을 통해 뷰포트 폭에 반영된다."""


def blend(fg: str, bg: str, ratio: float) -> str:
    """fg를 bg 위에 ratio 만큼 섞은 색. 은은한 선택 배경을 만드는 데 쓴다."""
    f, b = fg.lstrip("#"), bg.lstrip("#")
    parts = [round(int(f[i:i + 2], 16) * ratio + int(b[i:i + 2], 16) * (1 - ratio)) for i in (0, 2, 4)]
    return "#{:02X}{:02X}{:02X}".format(*parts)


def palette(theme: str = "dark") -> dict:
    """테마별 컬러 토큰.

    QSS와 아이콘 채색이 같은 값을 쓰도록 여기서만 정의한다.
    """
    if theme == "light":
        colors = {
            "bg": "#F2F4F7",
            "bg_alt": "#E7ECF2",
            "surface": "#FFFFFF",
            "border": "#DDE3EA",
            "border_strong": "#C4CDD8",
            "text": "#1B2430",
            "text_dim": "#66748A",
            "accent": "#00808F",
            "accent_hover": "#00707D",
            "accent_soft": "#B9D6DB",
            "primary": "#0FB0E6",
            "primary_hover": "#0C9AC9",
            "primary_press": "#0A83AB",
            "primary_fg": "#FFFFFF",
            "log_success": "#00808F",
            "notice": "#A94442",
            "warn": "#B8860B",
            "progress": "#6E5FA8",
            "ctx_download": "#6E5FA8",
            "ctx_history": "#9A7A15",
            "ctx_favorites": "#D24A44",
            "ctx_settings": "#3F8F72",
            "accent_fg": "#FFFFFF",
            "danger": "#9B3B47",
            "danger_hover": "#8A343F",
            "danger_fg": "#FFFFFF",
            "hover_red": "#D9534F",
            "hover_yellow": "#D9A521",
            "hover_green": "#3E9E6B",
        }
    else:
        colors = {
            "bg": "#161C26",
            "bg_alt": "#1B222D",
            "surface": "#1E2632",
            "border": "#2C3644",
            "border_strong": "#3C4859",
            "text": "#E6EBF2",
            "text_dim": "#8A97AA",
            "accent": "#2AB8C6",
            "accent_hover": "#45C6D2",
            "accent_soft": "#1B3A42",
            "primary": "#25C8FF",
            "primary_hover": "#52D6FF",
            "primary_press": "#0FA9DE",
            "primary_fg": "#04202B",
            "log_success": "#3FC9D6",
            "notice": "#FF9A94",
            "warn": "#E0A93B",
            "progress": "#9B8BE0",
            "ctx_download": "#9B8BE0",
            "ctx_history": "#FFF3C5",
            "ctx_favorites": "#FF6F69",
            "ctx_settings": "#96CEB4",
            "accent_fg": "#0E1620",
            "danger": "#D9636F",
            "danger_hover": "#E4808A",
            "danger_fg": "#10161F",
            "hover_red": "#FF7B74",
            "hover_yellow": "#F0C05A",
            "hover_green": "#6FD39B",
        }
    return colors


FILENAME_PART_COLORS = {
    "light": {
        "series": "#1F5FA9",
        "upload_date": "#0B6B5A",
        "episode_number": "#94500A",
        "episode": "#6A3FA0",
        "id": "#A83250",
    },
    "dark": {
        "series": "#6EB6FF",
        "upload_date": "#5FD9B0",
        "episode_number": "#FFB35C",
        "episode": "#C3A6FF",
        "id": "#FF8DA8",
    },
}
"""파일명 구성 요소마다 정해 둔 색.

목록의 항목과 미리보기의 같은 부분이 같은 색으로 보여야, 어느 것을 빼고
넣었을 때 파일명의 어디가 달라지는지 글을 읽지 않고 알 수 있다. 그래서
두 곳이 같은 값을 쓰도록 여기 한 곳에만 둔다.

색상환에서 고르게 떨어진 다섯 가지라 나란히 놓아도 서로 헷갈리지 않는다.
밝은 테마 쪽은 배경(#F2F4F7)에 묻히지 않도록 어둡게, 어두운 테마 쪽은
배경(#161C26)에 대비되도록 밝게 잡았다. 목록 배경과 미리보기 배경 어느
쪽에 얹혀도 명암비가 5를 넘는다.
"""

FILENAME_ROW_SELECT_MIX = 0.16
"""구성 요소 목록에서 고른 행에 까는 색의 비율. 창 배경에 accent를 섞는다.

더 진하게 깔면 조각 색 중 어두운 쪽(#94500A)이 그 위에서 읽히지 않는다.
0.16이면 다섯 색 모두 명암비 4.5를 넘기면서도 고른 행이 분명히 드러난다.
"""

FILENAME_PART_MUTED = 0.62
"""체크를 푼 항목의 색을 배경에 섞는 비율.

회색으로 바꾸지 않고 흐리게만 만든다. 색이 곧 그 항목의 이름표라, 회색이
되면 다시 켤 때 어느 자리가 돌아오는지 알 수 없다. 0.62면 켠 것과 뚜렷이
갈리면서 무슨 색이었는지는 남는다.
"""


ABOUT_HOVER_MIX = 0.22
"""정보 창 단추에 마우스를 올렸을 때 섞는 색의 비율.

창 배경에 섞어서 만든다. 고정 색을 박아 두면 밝은 테마에서는 옅고 어두운
테마에서는 눈이 아프게 튄다. 0.22면 어느 쪽에서도 글자가 그대로 읽힌다.
"""

ABOUT_BUTTON_SCALE = 0.84
"""닫기 단추 대비 정보 창 왼쪽 단추들의 크기 비율.

닫기가 이 창을 끝내는 단추라 가장 크고, 나머지는 곁들이는 일이라 한 단계
작게 둔다. 글꼴과 여백을 함께 줄여야 비율이 맞는다.
"""

MENU_RADIUS = 10
MENU_ITEM_RADIUS = 7
"""메뉴 바깥 모서리와 항목 강조 모서리.

항목 쪽을 더 작게 둔다. 같은 값이면 강조 사각형이 메뉴 테두리에 닿아 두 곡선이
겹쳐 보인다. RoundedMenu가 창 배경을 투명으로 만들 때 이 값이 실제 모서리가 된다.
"""

COMBO_POPUP_RADIUS = 10
COMBO_ITEM_RADIUS = 7
COMBO_POPUP_PADDING = 4
"""콤보박스 펼침 목록의 모서리와 여백. 모서리는 메뉴와 같은 값이다.

**여백을 창 높이에 맞춰 키우지 않는다.** 창 크기는 Qt가 먼저 정하고 우리 손은
그 뒤에 닿아서, 여백을 키우면 첫 번째 펼침에서만 목록이 잘린다(실측).

**같은 값을 쓰는 것이 요점이다.** 둘 다 제 창을 가진 팝업이고 하는 일도
'목록에서 하나 고르기'로 같아서, 모서리가 다르면 같은 화면에서 두 가지 규칙이
보인다. 메뉴 쪽을 고치면 이쪽도 함께 본다.

항목 반지름을 더 작게 두는 이유도 메뉴와 같다. 같은 값이면 강조 사각형이 바깥
테두리에 닿아 두 곡선이 겹쳐 보인다. 여백은 강조가 테두리에 닿지 않게 띄우는
몫이라, 이것이 0이면 반지름을 아무리 줄여도 모서리에서 만난다.
"""


def build_qss(theme: str = "dark") -> str:
    """선택된 테마에 맞는 QSS 문자열을 동적으로 생성합니다."""
    colors = palette(theme)
    ind = indicator_images(theme, colors)

    tint_dl = blend(colors["ctx_download"], colors["surface"], 0.18)
    tint_hi = blend(colors["ctx_history"], colors["surface"], 0.18)
    tint_fa = blend(colors["ctx_favorites"], colors["surface"], 0.18)

    order_sel = blend(colors["accent"], colors["bg"], FILENAME_ROW_SELECT_MIX)

    about_red = blend(colors["hover_red"], colors["bg"], ABOUT_HOVER_MIX)
    about_yellow = blend(colors["hover_yellow"], colors["bg"], ABOUT_HOVER_MIX)
    about_green = blend(colors["hover_green"], colors["bg"], ABOUT_HOVER_MIX)

    bump = 1
    fs_title = 15 + bump
    fs_pane = 13 + bump
    fs_card = 13 + bump
    fs_body = 12 + bump
    fs_sub = 11 + bump
    fs_num = 11 + bump

    mono = '"JetBrains Mono", "Consolas", "Cascadia Mono", "Pretendard Variable", "Pretendard JP", "Malgun Gothic"'

    return f"""
    /* 기본 */
    QWidget {{
        background: {colors["bg"]};
        color: {colors["text"]};
        font-family: {UI_FONT_STACK};
        font-size: {fs_body}px;
    }}
    QMainWindow, QDialog {{ background: {colors["bg"]}; }}

    /* 글자 위젯은 자기 배경을 칠하지 않는다.
       위의 QWidget 규칙이 QLabel/QCheckBox에도 적용돼, 카드(surface) 위에 얹힌
       제목·상태 문구마다 창 배경색(bg) 사각형이 겹쳐 보이던 원인이다. */
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
    #AppHeader {{ background: {colors["bg_alt"]}; border-bottom: 1px solid {colors["border"]}; }}
    #AppTitle {{ font-size: {fs_title + 2}px; font-weight: 600; color: {colors["text"]}; }}

    /* 버튼 — 3단계 위계 (UI_REDESIGN.md §1)
       2차가 기본값이다. 오브젝트명이 없는 모든 버튼이 여기 해당한다. */
    QPushButton {{
        background: transparent;
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 6px 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {colors["bg_alt"]}; border-color: {colors["border_strong"]}; }}
    QPushButton:pressed {{ background: {colors["border"]}; }}
    QPushButton:disabled {{ color: {colors["text_dim"]}; border-color: {colors["border"]}; background: transparent; }}

    /* 1차 — 화면당 하나 (다운로드, 저장) */
    QPushButton#PrimaryButton {{ background: {colors["primary"]}; color: {colors["primary_fg"]}; border-color: {colors["primary"]}; }}
    QPushButton#PrimaryButton:hover {{ background: {colors["primary_hover"]}; border-color: {colors["primary_hover"]}; }}
    QPushButton#PrimaryButton:pressed {{ background: {colors["primary_press"]}; border-color: {colors["primary_press"]}; }}
    /* 준비가 끝나기 전에도 같은 버튼으로 읽히도록 accent를 옅게 깔아 둔다.
       평범한 회색이면 준비 완료 순간 색이 튀어 다른 버튼처럼 보인다. */
    QPushButton#PrimaryButton:disabled {{
        background: {blend(colors["primary"], colors["surface"], 0.22)};
        color: {colors["text_dim"]};
        border-color: {blend(colors["primary"], colors["surface"], 0.35)};
    }}

    /* 위험 — 평소엔 2차, hover에서만 정체를 드러낸다 */
    QPushButton#DangerButton:hover {{ background: {colors["danger"]}; color: {colors["danger_fg"]}; border-color: {colors["danger"]}; }}
    QPushButton#DangerButton:pressed {{ background: {colors["danger_hover"]}; color: {colors["danger_fg"]}; border-color: {colors["danger_hover"]}; }}

    /* 링크 버튼 — 색 위계가 아니라 외부 링크임을 알리는 표시 */
    QPushButton#LinkButton {{ background: transparent; border: none; color: {colors["accent"]}; padding: 6px 4px; text-decoration: underline; }}
    QPushButton#LinkButton:hover {{ color: {colors["accent_hover"]}; background: transparent; }}

    /* 정보 창 왼쪽 단추 셋 — 닫기보다 한 단계 작고, 올리면 각자의 색이 든다.
       색을 달리하는 것은 세 단추가 하는 일이 서로 무관해서다. 나란히 같은
       모양으로 있으면 어느 것이 무엇인지 매번 글자를 읽어야 한다. */
    QPushButton#AboutYouTube, QPushButton#AboutContact, QPushButton#AboutUpdate {{
        font-size: {fs_sub}px;
        padding: 4px 11px;
        border-radius: 7px;
    }}
    QPushButton#AboutYouTube:hover {{
        background: {about_red}; border-color: {colors["hover_red"]};
    }}
    QPushButton#AboutContact:hover {{
        background: {about_yellow}; border-color: {colors["hover_yellow"]};
    }}
    QPushButton#AboutUpdate:hover {{
        background: {about_green}; border-color: {colors["hover_green"]};
    }}
    QPushButton#AboutUpdate:disabled {{
        background: transparent; border-color: {colors["border"]};
    }}

    /* 헤더 아이콘 버튼 — 클릭 영역 32x32, 아이콘 18px.
       hover 시 배경만 바뀐다(UI_REDESIGN.md 4항). 아이콘 색은 코드에서 칠한다. */
    QToolButton#IconButton {{
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 0px;
    }}
    QToolButton#IconButton:hover {{ background: {colors["surface"]}; }}
    QToolButton#IconButton:pressed {{ background: {colors["border"]}; }}
    QToolButton#IconButton:checked {{ background: {colors["accent_soft"]}; }}

    /* 카드 액션 버튼 — 완료 시 노출되는 재생 / 폴더 열기 */
    QToolButton#CardActionButton {{
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 0px;
    }}
    QToolButton#CardActionButton:hover {{ background: {colors["bg_alt"]}; }}
    QToolButton#CardActionButton:pressed {{ background: {colors["border"]}; }}

    /* 입력 */
    QLineEdit, QTextEdit, QSpinBox {{ background: {colors["surface"]}; border: 1px solid {colors["border"]}; border-radius: 8px; padding: 6px 8px; }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{ border: 1px solid {colors["accent"]}; }}
    QLineEdit#UrlInput {{ border-color: {colors["border_strong"]}; }}
    QLineEdit#UrlInput:focus {{ border: 1px solid {colors["accent"]}; }}
    QLineEdit#PathDisplayEdit {{ padding: 6px 8px; color: {colors["text_dim"]}; }}

    /* 콤보박스. 펼쳐지는 목록(QAbstractItemView)은 팝업 최상위 위젯이라
       본체 서체를 물려받지 않는다. 크기를 명시해야 설정창 안에서 일관되게 보인다.

       **여기서 그리는 둥근 상자가 실제로 보이는 팝업의 전부다.** 그것을 담은
       바깥 창은 apply_combo_popup_shape(src/widgets.py)가 투명으로 만든다.
       그 처리가 빠지면 이 둥근 상자 바깥에 사각형 창이 그대로 남아 테두리가
       이중으로 보인다. 모서리 값은 메뉴와 같은 것을 쓴다. */
    QComboBox {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 6px 8px;
        font-size: {fs_body}px;
        color: {colors["text"]};
    }}
    QComboBox:focus {{ border-color: {colors["accent"]}; }}
    QComboBox:disabled {{ color: {colors["text_dim"]}; background: {colors["bg_alt"]}; }}
    QComboBox QAbstractItemView {{
        background: {colors["surface"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: {COMBO_POPUP_RADIUS}px;
        padding: {COMBO_POPUP_PADDING}px;
        font-size: {fs_body}px;
        outline: none;
    }}
    /* 강조를 selection-background-color가 아니라 ::item에서 칠한다.
       그쪽은 행 상자를 통째로 채워서 둥근 모서리를 넘어 삐져나온다 - 목록에서
       고른 행에 각진 자국이 남던 것과 같은 성격이다. ::item에 반지름과 여백을
       주면 강조가 상자 안에 갇힌다. */
    QComboBox QAbstractItemView::item {{
        background: transparent;
        color: {colors["text"]};
        padding: 6px 10px;
        border-radius: {COMBO_ITEM_RADIUS}px;
        margin: 1px 2px;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {colors["accent"]};
        color: {colors["accent_fg"]};
    }}
    QComboBox QAbstractItemView::item:disabled {{ color: {colors["text_dim"]}; }}

    /* 체크박스·라디오 표시기. 라이트 테마에서 기본 표시기가 배경에 묻혀
       체크하는 곳인지조차 알기 어려웠다. 채움 여부로 상태가 분명해지게 한다. */
    QCheckBox::indicator, QRadioButton::indicator, QListWidget::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {colors["border_strong"]};
        background: {colors["surface"]};
    }}
    QCheckBox::indicator, QListWidget::indicator {{ border-radius: 4px; }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover, QListWidget::indicator:hover {{
        border-color: {colors["accent"]};
    }}
    QCheckBox::indicator:checked, QListWidget::indicator:checked {{
        background: {colors["accent"]};
        border: 1px solid {colors["accent"]};
        image: url("{ind["check"]}");
    }}
    QRadioButton::indicator:checked {{
        background: {colors["accent"]};
        border: 1px solid {colors["accent"]};
        image: url("{ind["dot"]}");
    }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
        background: {colors["bg_alt"]};
        border-color: {colors["border"]};
    }}

    /* 스핀박스 증감 버튼 — 기본 화살표가 작아 누르기 어렵다 */
    QSpinBox#StepperSpinBox {{ padding-right: 28px; }}
    QSpinBox#StepperSpinBox::up-button, QSpinBox#StepperSpinBox::down-button {{
        subcontrol-origin: border;
        width: 26px;
        background: {colors["bg_alt"]};
        border-left: 1px solid {colors["border"]};
    }}
    QSpinBox#StepperSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 8px; }}
    QSpinBox#StepperSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 8px; }}
    QSpinBox#StepperSpinBox::up-button:hover, QSpinBox#StepperSpinBox::down-button:hover {{
        background: {colors["border"]};
    }}
    QSpinBox#StepperSpinBox::up-arrow {{ image: url("{ind["arrow_up"]}"); width: 11px; height: 7px; }}
    QSpinBox#StepperSpinBox::down-arrow {{ image: url("{ind["arrow_down"]}"); width: 11px; height: 7px; }}

    /* 메뉴 — 트레이 우클릭과 목록 우클릭이 같은 모양을 쓴다.
       모서리를 둥글게 보이려면 QSS만으로는 안 되고 창 배경이 투명해야 한다.
       그쪽은 RoundedMenu(src/widgets.py)가 맡는다. */
    QMenu {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: {MENU_RADIUS}px;
        padding: 6px;
    }}
    QMenu::item {{
        background: transparent;
        color: {colors["text"]};
        padding: 8px 18px 8px 12px;
        border-radius: {MENU_ITEM_RADIUS}px;
        margin: 1px 2px;
    }}
    QMenu[checkmarks="true"]::item {{ padding-left: 34px; }}
    QMenu::item:selected {{ background: {colors["bg_alt"]}; }}
    QMenu::item:disabled {{ color: {colors["text_dim"]}; }}
    QMenu::separator {{ height: 1px; background: {colors["border"]}; margin: 5px 10px; }}
    QMenu::indicator {{ width: 16px; height: 16px; left: 11px; }}
    QMenu::indicator:checked {{ image: url("{ind["check_menu"]}"); }}

    /* 5) 종료 확인 등 메시지 상자 가운데 정렬 */
    QMessageBox QLabel {{ qproperty-alignment: 'AlignCenter'; }}
    QMessageBox QDialogButtonBox {{ qproperty-centerButtons: true; }}

    /* 파일명 구성 요소 목록 — 끌어서 차례를 바꾸는 곳이라 고른 행이 그대로 남는다.
       강조색을 정해 두지 않으면 그 자리가 새까맣게 찍혀, 조각마다 정해 둔 글자색이
       거기서만 묻힌다(PartColorDelegate가 색을 살려 놓아도 배경이 삼킨다). */
    QListWidget#FilenameOrderList::item {{ padding: 6px 8px; border-radius: 6px; }}
    QListWidget#FilenameOrderList::item:hover {{ background: {colors["bg_alt"]}; }}
    QListWidget#FilenameOrderList::item:selected {{ background: {order_sel}; }}

    /* 파일명 미리보기 */
    #FilenamePreview {{
        background: {colors["bg_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 6px;
        padding: 8px 10px;
        color: {colors["text"]};
    }}

    /* 그룹 상자 */
    QGroupBox {{
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        margin-top: 10px;
        padding: 14px 10px 10px 10px;
        font-size: {fs_body}px;
        font-weight: 600;
        color: {colors["text"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0px 4px;
        background: {colors["bg"]};
    }}
    QGroupBox:disabled {{ color: {colors["text_dim"]}; }}

    /* 설정창 좌측 세로 내비게이션 — 선택 항목에 3px accent 마커 (UI_REDESIGN.md 6항) */
    QListWidget#SettingsNav {{
        background: {colors["bg_alt"]};
        border: none;
        border-right: 1px solid {colors["border"]};
        padding: 8px 0px;
        outline: none;
    }}
    QListWidget#SettingsNav::item {{
        color: {colors["text_dim"]};
        border-left: 3px solid transparent;
        border-radius: 0px;
        padding: 8px 10px;
    }}
    QListWidget#SettingsNav::item:hover {{
        background: {colors["bg"]};
        color: {colors["text"]};
        border-radius: 0px;
    }}
    QListWidget#SettingsNav::item:selected {{
        background: {colors["surface"]};
        color: {colors["text"]};
        border-left: 3px solid {colors["ctx_settings"]};
        border-radius: 0px;
    }}

    /* 설정창 우측 상단의 현재 섹션 이름 */
    #SectionTitle {{ font-size: {fs_title + 2}px; font-weight: 600; color: {colors["text"]}; }}

    /* 단축키 설정 — 조합은 글자가 아니라 키라서, 로그·수치와 같은 고정폭으로 적는다.
       'Ctrl+I'와 'Ctrl+L'이 같은 폭으로 보여야 목록을 훑을 때 줄이 흔들리지 않는다. */
    QKeySequenceEdit QLineEdit {{ font-family: {mono}; font-size: {fs_body}px; }}
    #ShortcutWarning {{ color: {colors["danger"]}; font-size: {fs_sub}px; }}

    /* 세그먼트 컨트롤 — 알약 배경 안에서 선택된 항목만 떠오른다 (UI_REDESIGN.md 4항).
       QTabWidget 구조는 그대로 두고 탭 바 모양만 다시 그린다. */
    #MainTabs::pane {{ border: none; }}
    #MainTabs::tab-bar {{ alignment: left; left: 12px; }}
    #MainTabs QTabBar {{
        background: transparent;
        border: none;
    }}
    #MainTabs QTabBar::tab {{
        background: {colors["bg_alt"]};
        color: {colors["text_dim"]};
        border: 1px solid {colors["border"]};
        border-right: none;
        padding: 7px 16px;
        margin: 6px 0px 6px 0px;
        font-size: {fs_body}px;
        font-weight: 600;
    }}
    #MainTabs QTabBar::tab:first {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
    #MainTabs QTabBar::tab:last {{
        border-top-right-radius: 8px; border-bottom-right-radius: 8px;
        border-right: 1px solid {colors["border"]};
    }}
    #MainTabs QTabBar::tab:only-one {{ border-radius: 8px; border-right: 1px solid {colors["border"]}; }}
    #MainTabs QTabBar::tab:hover {{ color: {colors["text"]}; }}
    #MainTabs QTabBar::tab:selected {{
        background: {colors["surface"]};
        color: {colors["text"]};
    }}
    #PaneTitle {{ font-size: {fs_pane}px; font-weight: 600; color: {colors["text"]}; }}
    #PaneSubtitle {{ font-size: {fs_sub}px; font-weight: 400; color: {colors["text_dim"]}; }}

    /* 빈 목록 안내 — 둘 다 흐린 글자색이라 배경에 묻히고, 굵기와 크기로만 갈린다.
       목록에 카드가 하나라도 있으면 사라지는 글이라 눈길을 끌 이유가 없다. */
    #EmptyStateTitle {{ font-size: {fs_card}px; font-weight: 600; color: {colors["text_dim"]}; }}
    #EmptyStateText {{ font-size: {fs_sub}px; font-weight: 400; color: {colors["text_dim"]}; }}

    /* 리스트 */
    QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {{
        background: {colors["bg"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 4px;
    }}
    /* 카드가 자기 배경을 그리므로 행 자체는 거의 칠하지 않는다.
       원색으로 덮으면 카드 위 글자가 전부 묻힌다.

       고른 행에 생기던 사각 자국은 여기서 고칠 수 없다. 그것은 배경이 아니라
       초점 사각형이고, `outline: none`을 넣어 봐야 그대로 그려진다(실측).
       `NoFocusDelegate`(src/widgets.py)가 맡는다. */
    QListWidget#DownloadList::item, QListWidget#HistoryList::item,
    QListWidget#FavoritesList::item {{ background: transparent; border-radius: 10px; }}
    QListWidget#DownloadList::item:selected {{ background: {tint_dl}; }}
    QListWidget#HistoryList::item:selected {{ background: {tint_hi}; }}
    QListWidget#FavoritesList::item:selected {{ background: {tint_fa}; }}

    /* 카드 — 세 목록이 같은 모양을 쓴다 */
    #DownloadItem, #HistoryItem, #FavoriteItem {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
    }}
    #DownloadItem:hover, #HistoryItem:hover, #FavoriteItem:hover {{
        border-color: {colors["border_strong"]};
    }}
    /* 선택은 탭별 포인트 컬러로. 옅은 배경 + 테두리라 글자 대비를 해치지 않는다. */
    #DownloadItem[selected="true"] {{ background: {tint_dl}; border: 1px solid {colors["ctx_download"]}; }}
    #HistoryItem[selected="true"] {{ background: {tint_hi}; border: 1px solid {colors["ctx_history"]}; }}
    #FavoriteItem[selected="true"] {{ background: {tint_fa}; border: 1px solid {colors["ctx_favorites"]}; }}

    QLabel#Title {{ font-size: {fs_card}px; font-weight: 500; color: {colors["text"]}; }}
    /* 선택된 행은 강조 배경 위에 놓인다. 흐린 색 그대로면 읽히지 않는다.
       다크는 near-white, 라이트는 near-black으로 제목과 같은 색이 된다. */
    QLabel#Title[selected="true"],
    QLabel#Status[selected="true"],
    QLabel#PaneSubtitle[selected="true"] {{ color: {colors["text"]}; }}

    QLabel#Status {{ font-family: {mono}; font-size: {fs_num}px; font-weight: 500; color: {colors["text_dim"]}; }}
    QLabel#Thumb {{ background: {colors["bg"]}; border: 1px solid {colors["border"]}; border-radius: 4px; }}

    /* 진행바 — 높이 4px. 숫자는 옆의 퍼센트 라벨이 맡는다(UI_REDESIGN.md 5항). */
    QProgressBar#Progress {{ background: {colors["border"]}; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }}
    QProgressBar#Progress::chunk {{ border-radius: 2px; background: {colors["progress"]}; }}
    QProgressBar#Progress[state="done"]::chunk {{ background: {blend(colors["ctx_download"], colors["surface"], 0.55)}; }}
    QProgressBar#Progress[state="error"]::chunk {{ background: {colors["danger"]}; }}
    QProgressBar#Progress[state="warn"]::chunk {{ background: {colors["warn"]}; }}

    /* 구분선 */
    #Separator {{ background: {colors["border"]}; border: none; }}

    /* 로그 */
    #LogOutput {{ background: {colors["bg_alt"]}; border: 1px solid {colors["border"]}; border-radius: 8px; padding: 8px; }}

    /* 스크롤바 — 기본 스크롤바는 화살표 버튼까지 달려 투박하다.
       손잡이만 남긴 얇은 막대로 바꿔 어느 목록에서든 같은 모양으로 보이게 한다.
       즐겨찾기 목록은 칸 폭을 일정하게 유지하려고 스크롤바를 늘 띄워 두므로,
       스크롤할 것이 없을 때(손잡이가 홈을 꽉 채울 때)는 손잡이를 감춘다. */
    QScrollBar:vertical {{
        background: transparent;
        width: {SCROLLBAR_WIDTH}px;
        margin: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: {SCROLLBAR_WIDTH}px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {colors["border_strong"]};
        border-radius: {SCROLLBAR_WIDTH // 2}px;
        min-height: 36px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {colors["border_strong"]};
        border-radius: {SCROLLBAR_WIDTH // 2}px;
        min-width: 36px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {colors["text_dim"]};
    }}
    QScrollBar::handle:vertical:disabled, QScrollBar::handle:horizontal:disabled {{
        background: transparent;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0px; height: 0px; border: none; background: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """
