# src/utils.py

import json
import os
import sys
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QMessageBox

# OS 표시 언어별 앱 이름. 괄호 병기 없이 하나만 노출한다.
APP_NAME_FALLBACK = "TVer Downloader"
APP_NAME_BY_LANGUAGE = {
    QLocale.Language.Korean: "티버 다운로더",
    QLocale.Language.Japanese: "TVer ダウンローダー",
}


def localized_app_name(language: QLocale.Language | None = None) -> str:
    """OS 표시 언어에 맞는 앱 이름을 돌려준다. 모르는 언어면 영문 이름.

    language를 넘기면 그 언어로 계산한다(검증용). 평소에는 시스템 언어를 쓴다.
    """
    if language is None:
        language = QLocale.system().language()
    return APP_NAME_BY_LANGUAGE.get(language, APP_NAME_FALLBACK)


CONFIG_FILE = "downloader_config.json"
DEFAULT_PARALLEL = 5
PARALLEL_MIN = 1
PARALLEL_MAX = 20  # 수정: 최대 동시 다운로드 수 상향 (10 -> 20)
FILENAME_TITLE_MAX_LENGTH = 80  # 수정: 파일명 길이 제한 축소 (경로 길이 오류 방지)

# 실패로 간주하는 상태값. 편성 스트립 색과 재다운로드 메뉴가 함께 참조한다.
# TVerDownloader.py와 widgets.py 양쪽에서 쓰이므로 순환 참조를 피해 여기에 둔다.
ERROR_STATUSES = {"오류", "취소됨", "실패", "중단", "변환 오류"}


def get_resource_path(relative_path) -> Path:
    """개발 실행과 PyInstaller 번들(onefile/onedir) 양쪽에서 리소스 경로를 돌려준다.

    PyInstaller는 두 모드 모두에서 sys._MEIPASS를 설정한다(onedir은 _internal 폴더).
    번들이 아닐 때는 현재 작업 디렉터리가 아니라 이 파일이 속한 프로젝트 루트를 쓴다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return Path(base) / relative_path


def load_config() -> Dict[str, Any]:
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "light",
        "download_folder": "",
        "max_concurrent_downloads": DEFAULT_PARALLEL,
        "filename_parts": {
            "series": True, "upload_date": True, "episode_number": True,
            "episode": True, "id": True,
        },
        "filename_order": ["series", "upload_date", "episode_number", "episode", "id"],
        "quality": "bv*+ba/b",
        "preferred_codec": "original",  # 수정: 기본값을 '원본 유지'로 변경 (불필요한 재인코딩 방지)
        "auto_check_favorites_on_start": True,
        "always_on_top": False,
        "conversion_format": "none",
        "delete_on_conversion": False,
        "series_exclude_keywords": ["予告", "SP", "ダイジェスト", "ナビ", "解説放送版"],
        "hardware_encoder": "cpu",
        "quality_cpu_h264_crf": 26,
        "quality_cpu_h265_crf": 31,
        "quality_cpu_vp9_crf": 36,
        "quality_cpu_av1_crf": 41,
        "quality_gpu_cq": 30,
        "download_subtitles": True,
        "embed_subtitles": True,
        "subtitle_format": "vtt",
        "ignore_ssl_errors": False,
        # 닫기 버튼(X) 동작. exit=종료 확인 후 종료(기존 동작), tray=트레이로 이동
        "close_action": "exit",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                        config[k].update(v)
                    else:
                        config[k] = v
        except (json.JSONDecodeError, IOError):
            pass

    config["max_concurrent_downloads"] = canonicalize_config_parallel(config)
    return config


def save_config(config: dict) -> bool:
    """설정을 저장하고 성공 여부를 반환합니다. (실패를 조용히 삼키지 않음)"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except (IOError, OSError, TypeError):
        return False


def construct_filename_template(config: Dict[str, Any]) -> str:
    parts_cfg = config.get("filename_parts", {})
    order = config.get("filename_order", [])
    key_map = {
        "series": "%(series)s",
        "upload_date": "%(upload_date>%Y-%m-%d)s",
        "episode_number": "%(episode_number)s",
        "episode": "%(title)s",
        "id": "[%(id)s]"
    }
    selected_parts = [key_map[key] for key in order if parts_cfg.get(key, False) and key in key_map]
    if parts_cfg.get("series"):
        return f"%(series,playlist_title)s/{' '.join(selected_parts)}.%(ext)s"
    else:
        return f"{' '.join(selected_parts)}.%(ext)s"


def canonicalize_config_parallel(config: Dict[str, Any]) -> int:
    def clamp(n: Any) -> int:
        try:
            val = int(float(n))
            return max(PARALLEL_MIN, min(PARALLEL_MAX, val))
        except (ValueError, TypeError):
            return DEFAULT_PARALLEL

    if "max_concurrent_downloads" in config:
        return clamp(config["max_concurrent_downloads"])

    legacy_keys = [
        "max_parallel", "max_parallel_downloads", "parallel_downloads",
        "concurrent_downloads", "max_concurrent", "concurrency"
    ]
    for key in legacy_keys:
        if key in config:
            return clamp(config[key])

    for container_key in ["downloads", "download", "settings", "general", "app"]:
        if isinstance(config.get(container_key), dict):
            nested_dict = config[container_key]
            for key in ["max_parallel", "parallel", "concurrent", "max"]:
                if key in nested_dict:
                    return clamp(nested_dict[key])
    return DEFAULT_PARALLEL


def get_startupinfo():
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    return None


def open_file_location(filepath: str):
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", os.path.normpath(filepath)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", filepath])
        else:
            subprocess.run(["xdg-open", os.path.dirname(filepath)])
    except Exception:
        pass


def handle_exception(exc_type, exc_value, exc_traceback):
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_file = "TVerDownloader_crash.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(error_message)
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setWindowTitle("오류")
    error_box.setText("치명적인 오류가 발생했습니다.")
    error_box.setInformativeText(f"오류 상세가 '{log_file}' 파일에 저장되었습니다.")
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    error_box.exec()


def open_feedback_link():
    webbrowser.open("https://github.com/deuxdoom/TVerDownloader/issues")


def open_developer_link():
    webbrowser.open("https://www.youtube.com/@LE_SSERAFIM")