# -*- mode: python ; coding: utf-8 -*-
# TVerDownloader.spec — PyInstaller 6.x / onedir
#
#   빌드:  pyinstaller TVerDownloader.spec --noconfirm --clean
#   결과:  dist/TVerDownloader/TVerDownloader.exe
#
# bin/(yt-dlp.exe, ffmpeg.exe)은 의도적으로 번들하지 않는다.
# SetupThread가 실행 시점에 작업 디렉터리의 bin/으로 최신판을 내려받아 갱신하는
# 쓰기 대상이라, 번들에 넣으면 읽기 전용 위치(_internal)에 갇혀 자동 업데이트가 깨진다.
#
# downloader_config.json / favorites.json / thumbnails/ 도 같은 이유로 번들 대상이
# 아니다. 전부 프로세스의 작업 디렉터리 기준으로 생성되는 런타임 상태다.

import os
import PyQt6

APP_NAME = "TVerDownloader"

# Qt 기본 위젯 번역(입력창 우클릭 메뉴, 표준 대화상자 등).
# 이걸 빼면 OS 언어와 무관하게 영어로 나온다. 언어당 120~220KB.
QT_TRANSLATIONS_DIR = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "translations")
# 영어는 Qt에 내장돼 있어 파일이 필요 없다. 나머지 언어권은 영어로 통일한다.
TRANSLATION_LANGS = ["ko", "ja"]
TRANSLATION_DATAS = [
    (os.path.join(QT_TRANSLATIONS_DIR, f"qtbase_{lang}.qm"), "translations")
    for lang in TRANSLATION_LANGS
    if os.path.isfile(os.path.join(QT_TRANSLATIONS_DIR, f"qtbase_{lang}.qm"))
]

# 이 앱이 실제로 쓰는 Qt 바인딩은 QtCore/QtGui/QtWidgets/QtNetwork 넷뿐이다.
# 나머지는 제외해 배포 용량을 줄인다. (설치된 34개 중 30개)
EXCLUDED_QT = [
    "PyQt6.QtBluetooth", "PyQt6.QtDBus", "PyQt6.QtDesigner", "PyQt6.QtHelp",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtNfc",
    "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtPositioning", "PyQt6.QtPrintSupport", "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets", "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtSpatialAudio", "PyQt6.QtSql",
    # QtSvg는 제외하지 말 것 - src/icons.py가 QSvgRenderer로 Fluent 아이콘을 그린다.
    # 빼면 개발 환경에서는 멀쩡하고 빌드된 exe에서만 아이콘이 사라진다.
    "PyQt6.QtStateMachine", "PyQt6.QtSvgWidgets", "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtXml",
]

# 앱이 import하지 않는 표준 라이브러리 묶음.
# distutils는 넣지 말 것 — PyInstaller의 hook-distutils가 setuptools 벤더판을
# 별칭 등록하는데, 제외돼 있으면 ValueError로 빌드가 죽는다.
EXCLUDED_STDLIB = ["tkinter", "unittest", "test", "pydoc_data"]

a = Analysis(
    ["TVerDownloader.py"],
    pathex=[],
    binaries=[],
    # UI 서체. TVerDownloader.get_resource_path()가 sys._MEIPASS 기준으로 찾는다.
    # onedir에서는 _internal/assets/fonts/ 에 놓인다.
    # setup_app_font()가 등록하는 파일만 넣는다.
    datas=[
        ("assets/fonts/PretendardVariable.ttf", "assets/fonts"),    # 본문 (한글/라틴/가나)
        ("assets/fonts/PretendardJP-Regular.ttf", "assets/fonts"),  # 한자 (第3話 등)
        ("assets/fonts/JetBrainsMono-Regular.ttf", "assets/fonts"), # 수치 (고정폭)
        ("assets/logo", "assets/logo"),               # 헤더 로고 (언어 3종 x 테마 2종)
    ] + TRANSLATION_DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_STDLIB,
    noarchive=False,
    optimize=1,  # assert 제거. 2는 docstring까지 지우는데 그걸 읽는 라이브러리가 깨질 수 있다.
)

# ── 불필요한 번들 항목 제거 ────────────────────────────────────────────────
# PyQt6 훅은 Qt 바인딩을 excludes로 빼도 DLL과 플러그인은 의존성으로 딸려온다.
# 실제로 쓰지 않는 것들을 여기서 걷어낸다. 제거 내역은 빌드 로그에 [spec]으로 찍힌다.
DROP_BINARIES = {
    "opengl32sw.dll",   # 20MB. Qt의 소프트웨어 OpenGL 래스터라이저.
                        # QtWidgets는 raster 엔진으로 그리므로 쓰이지 않는다.
                        # GPU 드라이버가 없는 VM/RDP까지 대응하려면 이 항목을 지운다.
    "qt6pdf.dll",       # 4.5MB. qpdf 이미지 플러그인용. 이 앱은 PDF를 열지 않는다.
}
DROP_PATH_PARTS = (
    "qt6/translations/",              # 6.7MB. UI 문자열이 전부 코드에 한국어로 박혀 있다.
    "qt6/plugins/imageformats/qpdf",  # 위 Qt6Pdf.dll과 짝
)


def prune(entries, label):
    kept, dropped = [], []
    for entry in entries:
        dest = str(entry[0]).replace("\\", "/").lower()
        if dest.rsplit("/", 1)[-1] in DROP_BINARIES or any(p in dest for p in DROP_PATH_PARTS):
            dropped.append(dest)
        else:
            kept.append(entry)
    print("[spec] {}: {}개 제외".format(label, len(dropped)))
    for d in dropped:
        print("[spec]   - {}".format(d))
    return kept


a.binaries = prune(a.binaries, "binaries")
a.datas = prune(a.datas, "datas")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX는 켜지 않는다. Qt DLL 압축은 실행 실패를 자주 일으키고,
    # 백신 오탐(false positive)의 주된 원인이기도 하다.
    upx=False,
    console=False,          # GUI 앱. print()는 어디에도 보이지 않는다.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/tver.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
