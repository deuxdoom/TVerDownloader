# src/qss.py
# 수정: '항상 위' 버튼의 활성화(:checked) 스타일을 테마에 따라 다르게 적용

def build_qss(theme: str = "dark") -> str:
    """선택된 테마에 맞는 QSS 문자열을 동적으로 생성합니다."""
    
    if theme == "light":
        # 라이트 테마
        colors = {
            "bg_base": "#F9FAFB", "bg_alt": "#F3F4F6", "bg_widget": "#FFFFFF",
            "border": "#D1D5DB", "border_alt": "#E5E7EB",
            "text_pri": "#111827", "text_sec": "#4B5563", "text_subtle": "#9CA3AF",
            "primary": "#E0E7FF", "accent": "#3B82F6", "danger": "#EF4444",
            "success": "#10B981", "warning": "#F59E0B", "focus": "#FACC15",
            # 라이트 테마용 '항상 위' 활성화 색상
            "on_top_active_bg": "#4B5563", "on_top_active_fg": "#111827"
        }
    else:
        # 다크 테마
        colors = {
            "bg_base": "#0F0F10", "bg_alt": "#121214", "bg_widget": "#111214",
            "border": "#374151", "border_alt": "#1F2937",
            "text_pri": "#F3F4F6", "text_sec": "#E5E7EB", "text_subtle": "#9CA3AF",
            "primary": "#374151", "accent": "#3B82F6", "danger": "#EF4444",
            "success": "#22C55E", "warning": "#FACC15", "focus": "#FACC15",
            # 다크 테마용 '항상 위' 활성화 색상
            "on_top_active_bg": "#E5E7EB", "on_top_active_fg": "#F9FAFB"
        }

    return f"""
    /* 기본 */
    QWidget {{
        background: {colors["bg_base"]};
        color: {colors["text_sec"]};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {colors["bg_base"]}; }}
    #AppHeader {{ background: {colors["bg_alt"]}; border-bottom: 1px solid {colors["border_alt"]}; }}
    #AppTitle {{ font-size: 16px; font-weight: 600; color: {colors["text_pri"]}; }}

    /* 버튼 공통 */
    QPushButton#PrimaryButton, QPushButton#AccentButton, QPushButton#DangerButton, 
    QPushButton#GhostButton, QPushButton#OrangeButton, QPushButton#PurpleButton,
    QPushButton#InfoButton {{ padding: 6px 12px; border-radius: 8px; border: 1px solid transparent; font-weight: 600; }}
    QPushButton:hover {{ filter: brightness(1.05); }}
    QPushButton:pressed {{ padding-top: 8px; filter: brightness(0.95); }}
    QPushButton:disabled {{ opacity: .6; }}

    /* 버튼 개별 색상 */
    QPushButton#PrimaryButton {{ background: {colors["primary"]}; color: {colors["text_pri"]}; }}
    QPushButton#AccentButton {{ background: {colors["accent"]}; color: white; }}
    QPushButton#DangerButton {{ background: {colors["danger"]}; color: white; }}
    QPushButton#GhostButton {{ background: transparent; color: {colors["text_subtle"]}; border-color: {colors["border"]}; }}
    QPushButton#OrangeButton {{ background: #F97316; color: white; }}
    QPushButton#PurpleButton {{ background: #8B5CF6; color: white; }}
    QPushButton#InfoButton {{ background: {colors["success"]}; color: white; }}

    /* '항상 위' 버튼 스타일 */
    QToolButton#OnTopButton {{
        background: transparent;
        border: none;
        font-size: 16px;
        padding: 2px;
        color: {colors["text_subtle"]};
    }}
    QToolButton#OnTopButton:hover {{
        background: {colors["bg_alt"]};
        border-radius: 4px;
    }}
    QToolButton#OnTopButton:checked {{
        background: {colors["on_top_active_bg"]};
        color: {colors["on_top_active_fg"]};
        border-radius: 4px;
    }}

    /* 입력 */
    QLineEdit, QTextEdit, QSpinBox {{ background: {colors["bg_widget"]}; border: 1px solid {colors["border"]}; border-radius: 8px; padding: 6px 8px; }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{ border: 1px solid {colors["accent"]}; }}
    QLineEdit#UrlInput {{ border-color: {colors["text_sec"]}; }}
    QLineEdit#UrlInput:focus {{
        border: 1px solid {colors["focus"]};
    }}
    QLineEdit#PathDisplayEdit {{ padding: 6px 8px; color: {colors["text_subtle"]}; }}

    /* 탭/패널 */
    #MainTabs::pane {{ border: none; }}
    QTabBar::tab {{ background: {colors["bg_base"]}; color: {colors["text_subtle"]}; padding: 10px 20px; border: none; font-weight: 600; }}
    QTabBar::tab:hover {{ background: {colors["bg_alt"]}; }}
    QTabBar::tab:selected {{ background: {colors["bg_alt"]}; color: {colors["text_pri"]}; border-top: 2px solid {colors["warning"]}; }}
    #PaneTitle {{ color: {colors["text_pri"]}; font-weight: 600; }}
    #PaneSubtitle {{ color: {colors["text_subtle"]}; }}

    /* 리스트 */
    QListWidget#DownloadList, QListWidget#HistoryList, QListWidget#FavoritesList {{ background: {colors["bg_base"]}; border: 1px solid {colors["border_alt"]}; border-radius: 8px; padding: 0px; }}
    QListWidget::item:hover {{ background: {colors["bg_alt"]}; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {colors["accent"]}; color: white; border-radius: 6px; }}

    /* 아이템 위젯 */
    #DownloadItem {{ background: {colors["bg_widget"]}; border: 1px solid {colors["border_alt"]}; border-radius: 10px; }}
    #DownloadItem:hover {{ border-color: {colors["border"]}; }}
    #FavoriteItem, #HistoryItem {{ border-bottom: 1px solid {colors["border_alt"]}; }}
    QListWidget#HistoryList::item {{ border-bottom: 1px solid {colors["border_alt"]}; padding: 8px; }}
    
    QLabel#Title {{ font-weight: 600; color: {colors["text_pri"]}; }}
    QLabel#Status {{ color: {colors["text_subtle"]}; }}
    QLabel#Thumb {{ background: {colors["bg_base"]}; border: 1px solid {colors["border_alt"]}; border-radius: 6px; }}

    /* 진행바 */
    QProgressBar#Progress {{ background: {colors["bg_alt"]}; border: 1px solid {colors["border_alt"]}; border-radius: 7px; min-height: 14px; max-height: 14px; text-align: center;}}
    QProgressBar#Progress::chunk {{ border-radius: 7px; background: {colors["accent"]}; }}
    QProgressBar#Progress[state="done"]::chunk {{ background: {colors["success"]}; }}
    QProgressBar#Progress[state="error"]::chunk {{ background: {colors["danger"]}; }}

    /* 로그 */
    #LogOutput {{ background: {colors["bg_alt"]}; border: 1px solid {colors["border_alt"]}; border-radius: 8px; padding: 8px; }}
    """