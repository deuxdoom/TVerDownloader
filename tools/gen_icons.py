"""assets/icons/*.svg 를 읽어 src/icons_data.py 로 임베드한다.

아이콘을 추가하거나 교체한 뒤 다시 돌리면 된다:
    python tools/gen_icons.py

SVG는 텍스트라 Base64로 감싸지 않고 원문 그대로 넣는다. 디코딩 단계가 없어
fill 치환이 문자열 replace 한 번으로 끝나고, 어떤 아이콘이 바뀌었는지 diff에 드러난다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "assets" / "icons"
OUT = ROOT / "src" / "icons_data.py"

FLUENT_FILL = "#212121"

ICON_FILES = {
    "settings": "ic_fluent_settings_20_regular.svg",
    "theme_dark": "ic_fluent_weather_moon_20_regular.svg",
    "theme_light": "ic_fluent_weather_sunny_20_regular.svg",
    "pin": "ic_fluent_pin_20_regular.svg",
    "pin_on": "ic_fluent_pin_20_filled.svg",
    "info": "ic_fluent_info_20_regular.svg",
    "download": "ic_fluent_arrow_download_20_regular.svg",
    "bulk_add": "ic_fluent_grid_20_regular.svg",
    "play": "ic_fluent_play_20_regular.svg",
    "folder_open": "ic_fluent_folder_open_20_regular.svg",
    "cancel": "ic_fluent_dismiss_20_regular.svg",
    "nav_filename": "ic_fluent_document_text_20_regular.svg",
    "nav_quality": "ic_fluent_video_20_regular.svg",
    "nav_subtitle": "ic_fluent_subtitles_20_regular.svg",
    "nav_advanced": "ic_fluent_wrench_20_regular.svg",
    "nav_cache": "ic_fluent_delete_20_regular.svg",
    "nav_shortcut": "ic_keyboard_20_regular.svg",
    "log": "ic_fluent_document_table_20_regular.svg",
    "tab_history": "ic_fluent_history_20_regular.svg",
    "tab_favorites": "ic_fluent_star_20_regular.svg",
}


def compact(svg: str) -> str:
    """XML 선언과 주석, 태그 사이 공백을 걷어내 한 줄로 만든다."""
    svg = re.sub(r"<\?xml.*?\?>", "", svg, flags=re.DOTALL)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    svg = re.sub(r">\s+<", "><", svg)
    return " ".join(svg.split())


def main() -> int:
    missing = [(n, f) for n, f in ICON_FILES.items() if not (SRC_DIR / f).is_file()]
    if missing:
        print(f"원본 SVG {len(missing)}개를 찾지 못해 건너뜁니다:", file=sys.stderr)
        for name, f in missing:
            print(f"  [{name}] {SRC_DIR / f}", file=sys.stderr)

    lines = [
        '"""src/icons_data.py — 자동 생성 파일. 직접 수정하지 마세요.',
        "",
        "생성: python tools/gen_icons.py",
        "원본: assets/icons/*.svg",
        "",
        "Fluent UI System Icons (c) Microsoft Corporation, MIT License",
        "https://github.com/microsoft/fluentui-system-icons",
        '"""',
        "",
        "ICON_SVG = {",
    ]
    warnings = 0
    skipped = {n for n, _ in missing}
    for name, filename in ICON_FILES.items():
        if name in skipped:
            continue
        svg = compact((SRC_DIR / filename).read_text(encoding="utf-8"))
        if FLUENT_FILL not in svg:
            print(f"경고: {filename} 에 {FLUENT_FILL} 가 없어 테마 색이 적용되지 않습니다.", file=sys.stderr)
            warnings += 1
        lines.append(f"    {name!r}: {svg!r},")
    lines.append("}")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} 생성 완료 - 아이콘 {len(ICON_FILES) - len(missing)}개"
          f" (건너뜀 {len(missing)}, 경고 {warnings})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
