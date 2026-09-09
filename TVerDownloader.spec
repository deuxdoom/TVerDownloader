import importlib.util
import os
import shutil

import PyQt6
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

APP_NAME = "TVerDownloader"
APP_PUBLISHER = "deuxdoom"
APP_DESCRIPTION = "TVer Downloader"


def read_app_version():
    """버전은 versioninfo.py 한 줄에서만 온다 - 여기 숫자를 적어 두면 둘이 조용히 어긋난다."""
    finder = importlib.util.spec_from_file_location(
        "_tvd_versioninfo", os.path.join(SPECPATH, "versioninfo.py")
    )
    module = importlib.util.module_from_spec(finder)
    finder.loader.exec_module(module)
    return module.APP_VERSION


def build_version_resource(version):
    """윈도우 버전 리소스. CompanyName이 작업 관리자 시작 프로그램 탭의 '게시자'로 나온다.

    리소스가 네 자리를 요구해서 세 자리 버전 뒤에 0을 붙인다.
    """
    numbers = tuple(int(part) for part in version.split(".")) + (0,)
    strings = [
        StringStruct("CompanyName", APP_PUBLISHER),
        StringStruct("FileDescription", APP_DESCRIPTION),
        StringStruct("FileVersion", version),
        StringStruct("InternalName", APP_NAME),
        StringStruct("LegalCopyright", "Copyright (c) " + APP_PUBLISHER),
        StringStruct("OriginalFilename", APP_NAME + ".exe"),
        StringStruct("ProductName", APP_DESCRIPTION),
        StringStruct("ProductVersion", version),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("041204B0", strings)]),
            VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
        ],
    )


APP_VERSION = read_app_version()
VERSION_RESOURCE = build_version_resource(APP_VERSION)

QT_TRANSLATIONS_DIR = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "translations")
TRANSLATION_LANGS = ["ko", "ja", "en", "es", "zh_CN", "zh_TW"]
"""배포본에 실을 Qt 기본 위젯 번역. `lang/`에 있는 일곱 언어에 맞춘다.

입력칸 우클릭 메뉴와 QMessageBox 기본 단추가 이 파일에서 나온다. 빠뜨린 언어는 그 자리만
영어가 되어, 앱은 그 언어인데 메뉴만 영어인 상태가 된다. 태국어는 Qt에 qtbase 번역이 없어
뺐고, en은 33바이트뿐이라 넣어 두면 "찾지 못했습니다" 안내가 뜨지 않는다. 여섯을 합쳐 708KB다.
"""
TRANSLATION_DATAS = [
    (os.path.join(QT_TRANSLATIONS_DIR, f"qtbase_{lang}.qm"), "translations")
    for lang in TRANSLATION_LANGS
    if os.path.isfile(os.path.join(QT_TRANSLATIONS_DIR, f"qtbase_{lang}.qm"))
]

EXCLUDED_QT = [
    "PyQt6.QtBluetooth", "PyQt6.QtDBus", "PyQt6.QtDesigner", "PyQt6.QtHelp",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtNfc",
    "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtPositioning", "PyQt6.QtPrintSupport", "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets", "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtSpatialAudio", "PyQt6.QtSql",
    # QtSvg는 제외하지 말 것 — 빼면 개발 환경은 멀쩡하고 빌드된 exe에서만 아이콘이 사라진다
    "PyQt6.QtStateMachine", "PyQt6.QtSvgWidgets", "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtXml",
]

# distutils는 넣지 말 것 — ValueError로 빌드가 죽는다
EXCLUDED_STDLIB = ["tkinter", "unittest", "test", "pydoc_data"]

a = Analysis(
    ["TVerDownloader.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/fonts/PretendardVariable.ttf", "assets/fonts"),
        ("assets/fonts/PretendardJP-Regular.ttf", "assets/fonts"),
        ("assets/fonts/JetBrainsMono-Regular.ttf", "assets/fonts"),
        ("assets/title", "assets/title"),
        ("assets/appicon.ico", "assets"),
        ("lang", "lang"),
    ] + TRANSLATION_DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_STDLIB,
    noarchive=False,
    optimize=1,
)

DROP_BINARIES = {
    "opengl32sw.dll",
    "qt6pdf.dll",
}
DROP_PATH_PARTS = (
    "qt6/translations/",
    "qt6/plugins/imageformats/qpdf",
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/appicon.ico",
    version=VERSION_RESOURCE,
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


README_SOURCE = "readme.txt"
README_SHIPPED = "도움말(README).txt"
"""배포본에서만 이름을 바꿔 단다. 쓰는 사람 대다수가 한국어라 `readme`보다
`도움말`이 먼저 읽히고, 괄호 안의 README가 영어권 사용자에게 같은 것임을 알린다.
저장소 쪽은 `readme.txt` 그대로 둔다 - 도구와 편집기가 알아보는 이름이다."""


def install_readme():
    """안내문을 exe 바로 옆에 둔다.

    datas로 넣으면 PyInstaller 6이 `_internal/` 안에 넣는데, 이 파일은 사용자가 열어
    보라고 두는 것이라 거기 있으면 눈에 띄지 않는다. COLLECT가 끝나면 dist 폴더가
    이미 만들어져 있으므로 그 뒤에 복사한다.
    """
    shutil.copyfile(os.path.join(SPECPATH, README_SOURCE),
                    os.path.join(DISTPATH, APP_NAME, README_SHIPPED))


install_readme()
