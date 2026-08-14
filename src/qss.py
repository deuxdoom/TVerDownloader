# src/qss.py
# UI_REDESIGN.md 1단계: 컬러 토큰 정리 + 버튼 위계 3단계 축소
# UI_REDESIGN.md 2단계: 타입 스케일 (15/13/13/12/11px) + 수치용 고정폭

from src.indicators import indicator_images


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
            "bg": "#F2F4F7",            # 앱 배경
            "bg_alt": "#E7ECF2",        # hover, 살짝 눌린 면
            "surface": "#FFFFFF",       # 카드·패널 표면
            "border": "#DDE3EA",
            "border_strong": "#C4CDD8", # 입력창처럼 존재감이 필요한 테두리
            "text": "#1B2430",
            "text_dim": "#66748A",
            "accent": "#00808F",        # 浅葱(아사기) — 포커스, 체크, 링크 등 일반 상호작용
            "accent_hover": "#00707D",
            "accent_press": "#005F6A",
            "accent_soft": "#B9D6DB",
            "accent_dim": "#4D9CA6",
            # 1차 동작(다운로드·저장) 전용. 여기만 밝은 파랑을 쓴다.
            "primary": "#0FB0E6",
            "primary_hover": "#0C9AC9",
            "primary_press": "#0A83AB",
            "primary_fg": "#FFFFFF",    # 라이트에서는 흰 글자
            "log_success": "#00808F",   # 로그의 완료/성공 문구 (浅葱 계열)
            "progress": "#6E5FA8",      # 藤(후지) — 진행 중. 선택 하이라이트와 색 계열을 분리한다
            # 탭별 포인트 컬러. 서로 다른 화면에만 나타나 한 번에 둘 이상 보이지 않는다.
            "ctx_download": "#6E5FA8",   # 藤 — 다운로드
            "ctx_history": "#9A7A15",    # 기록 (다크의 #FFF3C5를 라이트용으로 낮춘 값)
            "ctx_favorites": "#D24A44",  # 즐겨찾기 (다크의 #FF6F69 대응)
            "ctx_settings": "#3F8F72",   # 설정 (다크의 #96CEB4 대응)
            "accent_fg": "#FFFFFF",     # accent 채움 위 글자색
            "warn": "#B8860B",          # 黄檗(키하다) — 4단계 편성 스트립에서 사용 예정
            "danger": "#9B3B47",        # 蘇芳(스오)
            "danger_hover": "#8A343F",
            "danger_fg": "#FFFFFF",
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
            "accent_press": "#1F9AA6",
            "accent_soft": "#1B3A42",
            "accent_dim": "#1E7C86",
            "primary": "#25C8FF",
            "primary_hover": "#52D6FF",
            "primary_press": "#0FA9DE",
            "primary_fg": "#04202B",
            "log_success": "#3FC9D6",
            "progress": "#9B8BE0",      # 藤(후지) — 진행 중
            "ctx_download": "#9B8BE0",   # 藤
            "ctx_history": "#FFF3C5",
            "ctx_favorites": "#FF6F69",
            "ctx_settings": "#96CEB4",
            "accent_fg": "#0E1620",     # 밝은 청록 위에는 어두운 글자가 대비를 확보한다
            "warn": "#D9A22B",
            "danger": "#D9636F",
            "danger_hover": "#E4808A",
            "danger_fg": "#10161F",
        }
    return colors


def build_qss(theme: str = "dark") -> str:
    """선택된 테마에 맞는 QSS 문자열을 동적으로 생성합니다."""
    colors = palette(theme)
    ind = indicator_images(theme, colors)

    # 선택된 카드 배경. 원색으로 덮으면 글자가 묻히므로 표면 위에 옅게 섞는다.
    tint_dl = blend(colors["ctx_download"], colors["surface"], 0.18)
    tint_hi = blend(colors["ctx_history"], colors["surface"], 0.18)
    tint_fa = blend(colors["ctx_favorites"], colors["surface"], 0.18)

    # 타입 스케일. UI_REDESIGN.md §2 기준값 + SCALE_BUMP.
    # 문서 기준값(15/13/13/12/11)이 고해상도 모니터에서 작게 읽혀 한 단계 올렸다.
    # 전체 크기를 조절하려면 SCALE_BUMP 하나만 바꾸면 위계는 그대로 유지된다.
    bump = 1
    fs_title = 15 + bump   # 앱 헤더
    fs_pane = 13 + bump    # 패널 제목
    fs_card = 13 + bump    # 카드 제목
    fs_body = 12 + bump    # 본문·라벨
    fs_sub = 11 + bump     # 보조 정보
    fs_num = 11 + bump     # 수치

    # 수치(진행률·용량·속도)용 고정폭. JetBrains Mono를 번들하고, 등록에 실패하면
    # Windows 기본 고정폭으로 내려간다.
    # 뒤쪽 본문 서체는 같은 라벨에 섞이는 한글·한자용이다 — 고정폭 서체에는 없는 글자다.
    mono = '"JetBrains Mono", "Consolas", "Cascadia Mono", "Pretendard Variable", "Pretendard JP", "Malgun Gothic"'

    return f"""
    /* 기본 */
    QWidget {{
        background: {colors["bg"]};
        color: {colors["text"]};
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
       본체 서체를 물려받지 않는다. 크기를 명시해야 설정창 안에서 일관되게 보인다. */
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
        border-radius: 8px;
        padding: 4px;
        font-size: {fs_body}px;
        outline: none;
        selection-background-color: {colors["accent"]};
        selection-color: {colors["accent_fg"]};
    }}

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

    /* 5) 종료 확인 등 메시지 상자 가운데 정렬 */
    QMessageBox QLabel {{ qproperty-alignment: 'AlignCenter'; }}
    QMessageBox QDialogButtonBox {{ qproperty-centerButtons: true; }}

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

    /* 리스트 */
    QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {{
        background: {colors["bg"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 4px;
    }}
    /* 카드가 자기 배경을 그리므로 행 자체는 거의 칠하지 않는다.
       원색으로 덮으면 카드 위 글자가 전부 묻힌다. */
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

    /* 구분선 */
    #Separator {{ background: {colors["border"]}; border: none; }}

    /* 로그 */
    #LogOutput {{ background: {colors["bg_alt"]}; border: 1px solid {colors["border"]}; border-radius: 8px; padding: 8px; }}
    """
