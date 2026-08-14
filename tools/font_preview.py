# tools/font_preview.py
"""글자 렌더링 옵션 조합을 한 화면에서 눈으로 비교한다.

    python tools/font_preview.py

앱과 똑같은 서체·크기·QSS로 실제 QLabel을 그리므로, 여기서 좋아 보이는 조합이
앱에서도 그대로 나온다. 마음에 드는 줄의 번호를 고른 뒤 TVerDownloader.py의
UI_FONT_HINTING / UI_FONT_STYLE_STRATEGY 두 상수만 그 값으로 바꾸면 된다.

측정으로는 판별이 안 되는 문제라(안티앨리어싱은 이미 켜져 있고 서브픽셀도 동작 중),
결국 사람 눈으로 고르는 게 맞다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
)

from src.qss import build_qss, palette

H = QFont.HintingPreference
S = QFont.StyleStrategy

# (표시 이름, 힌팅, 스타일 전략)  — 전략 None = Windows ClearType 설정을 그대로 따름
COMBOS = [
    ("1. Full + Antialias|Quality  (현재 설정)", H.PreferFullHinting, S.PreferAntialias | S.PreferQuality),
    ("2. Full + 전략 미지정",                     H.PreferFullHinting, None),
    ("3. Vertical + Antialias|Quality",           H.PreferVerticalHinting, S.PreferAntialias | S.PreferQuality),
    ("4. Vertical + 전략 미지정",                  H.PreferVerticalHinting, None),
    ("5. None + Antialias|Quality",               H.PreferNoHinting, S.PreferAntialias | S.PreferQuality),
    ("6. None + 전략 미지정",                      H.PreferNoHinting, None),
    ("7. Default + 전략 미지정",                   H.PreferDefaultHinting, None),
]

# 앱의 타입 스케일 (qss.py의 bump=1 기준)
ROWS = [(13, 400, "본문 13/400"), (14, 500, "카드 14/500"), (16, 600, "헤더 16/600")]
SAMPLE = "다운로드 완료  テスト番組 第3話  12.4MB/s"

FONT_FILES = [
    "assets/fonts/PretendardVariable.ttf",
    "assets/fonts/PretendardJP-Regular.ttf",
    "assets/fonts/JetBrainsMono-Regular.ttf",
]


def main() -> int:
    app = QApplication(sys.argv)

    families = []
    for path in FONT_FILES:
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id != -1:
            families.append(QFontDatabase.applicationFontFamilies(font_id)[0])
    if not families:
        print("assets/fonts/ 에서 서체를 불러오지 못했습니다. 프로젝트 루트에서 실행하세요.", file=sys.stderr)
        return 1

    theme = sys.argv[1] if len(sys.argv) > 1 else "light"
    app.setStyleSheet(build_qss(theme))
    colors = palette(theme)

    root = QWidget()
    root.setWindowTitle(f"글자 렌더링 비교 - {theme} (인자로 light/dark 지정 가능)")
    outer = QVBoxLayout(root)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    inner = QWidget()
    grid = QGridLayout(inner)
    grid.setContentsMargins(16, 16, 16, 16)
    grid.setHorizontalSpacing(20)
    grid.setVerticalSpacing(6)

    row = 0
    for name, hinting, strategy in COMBOS:
        header = QLabel(name)
        header.setStyleSheet(f"color:{colors['accent']}; font-weight:600;")
        grid.addWidget(header, row, 0, 1, 2)
        row += 1

        for px, weight, tag in ROWS:
            font = QFont()
            font.setFamilies(families[:1] + ["Pretendard JP", "Malgun Gothic"])
            font.setPixelSize(px)
            font.setWeight(weight)
            font.setHintingPreference(hinting)
            if strategy is not None:
                font.setStyleStrategy(strategy)

            tag_label = QLabel(tag)
            tag_label.setStyleSheet(f"color:{colors['text_dim']};")
            tag_label.setFont(font)
            sample = QLabel(SAMPLE)
            sample.setFont(font)
            sample.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            grid.addWidget(tag_label, row, 0)
            grid.addWidget(sample, row, 1)
            row += 1

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background:{colors['border']}; border:none;")
        line.setFixedHeight(1)
        grid.addWidget(line, row, 0, 1, 2)
        row += 1

    grid.setColumnStretch(1, 1)
    scroll.setWidget(inner)
    outer.addWidget(scroll)

    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    note = QLabel(
        f"현재 화면 배율(devicePixelRatio) = {dpr}    "
        "가장 깔끔해 보이는 조합의 번호를 알려주세요."
    )
    note.setStyleSheet(f"color:{colors['text_dim']}; padding:4px 16px;")
    outer.addWidget(note)

    root.resize(760, 900)
    root.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
