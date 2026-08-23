import importlib.util
import os

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
TRANSLATION_LANGS = ["ko", "ja"]
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
        ("assets/logo", "assets/logo"),
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
    icon="assets/tver.ico",
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
