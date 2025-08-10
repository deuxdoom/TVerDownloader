# src/utils.py
# 수정:
# - FILENAME_TITLE_MAX_LENGTH: 파일명에 사용될 제목의 최대 길이를 80자로 정의
# - construct_filename_template: 생성되는 파일명 템플릿에서 제목 부분에 길이 제한 구문을 적용

import json
import os
import sys
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QMessageBox

CONFIG_FILE = "downloader_config.json"
DEFAULT_PARALLEL = 3
PARALLEL_MIN = 1
PARALLEL_MAX = 5
# 파일명으로 사용될 동영상 제목의 최대 길이 (OS 경로 길이 제한 오류 방지)
FILENAME_TITLE_MAX_LENGTH = 80


def load_config() -> Dict[str, Any]:
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "dark",
        "download_folder": "",
        "max_concurrent_downloads": DEFAULT_PARALLEL,
        "filename_parts": {
            "series": True,
            "upload_date": True,
            "episode_number": True,
            "episode": True,
            "id": True,
        },
        "filename_order": ["series", "upload_date", "episode_number", "episode", "id"],
        "post_action": "None",
        "quality": "bv*+ba/b",
        "auto_check_favorites_on_start": True,
        "always_on_top": False
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


def save_config(config: dict):
    """설정 파일 저장."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except IOError:
        pass


def construct_filename_template(config: Dict[str, Any]) -> str:
    """
    설정값에서 파일명 순서와 사용 여부를 조합하여 yt-dlp용 출력 템플릿을 생성합니다.
    """
    parts_cfg = config.get("filename_parts", {})
    order = config.get("filename_order", [])

    # yt-dlp가 인식하는 형식으로 변환
    key_map = {
        "series": "%(series)s",
        "upload_date": "%(upload_date>%Y-%m-%d)s",
        "episode_number": "%(episode_number)s",
        "episode": f"%(title:.{FILENAME_TITLE_MAX_LENGTH})s", # 제목(episode)에 길이 제한 적용
        "id": "[%(id)s]"
    }
    
    selected_parts = [key_map[key] for key in order if parts_cfg.get(key, False) and key in key_map]
    
    # 시리즈명이 있으면 하위 폴더로, 없으면 현재 폴더로
    if parts_cfg.get("series"):
        # TVer는 series 메타가 없을 때 playlist_title을 대신 사용하기도 함
        return f"%(series,playlist_title)s/{' '.join(selected_parts)}.%(ext)s"
    else:
        return f"{' '.join(selected_parts)}.%(ext)s"


def canonicalize_config_parallel(config: Dict[str, Any]) -> int:
    """
    다양한 키 이름으로 저장될 수 있는 동시 다운로드 설정값을 정규화하여 단일 키로 통합합니다.
    """
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
    """Windows에서 서브프로세스 콘솔 숨김."""
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    return None


def open_file_location(filepath: str):
    """파일 탐색기에서 파일 위치 열기(플랫폼별)."""
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
    """글로벌 예외 핸들러: 로그 파일로 저장하고 메시지 박스 알림."""
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