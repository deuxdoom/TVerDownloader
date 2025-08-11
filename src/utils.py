# src/utils.py
# 수정: load_config에 '변환 후 원본 삭제' 옵션(delete_on_conversion) 기본값 추가

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
FILENAME_TITLE_MAX_LENGTH = 120


def load_config() -> Dict[str, Any]:
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "dark",
        "download_folder": "",
        "max_concurrent_downloads": DEFAULT_PARALLEL,
        "filename_parts": {
            "series": True, "upload_date": True, "episode_number": True,
            "episode": True, "id": True,
        },
        "filename_order": ["series", "upload_date", "episode_number", "episode", "id"],
        "post_action": "None",
        "quality": "bv*+ba/b",
        "auto_check_favorites_on_start": True,
        "always_on_top": False,
        "bandwidth_limit": "0",
        "conversion_format": "none",
        "delete_on_conversion": False  # 변환 후 원본 삭제 여부
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
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except IOError:
        pass

def construct_filename_template(config: Dict[str, Any]) -> str:
    parts_cfg = config.get("filename_parts", {})
    order = config.get("filename_order", [])
    key_map = {
        "series": "%(series)s", "upload_date": "%(upload_date>%Y-%m-%d)s",
        "episode_number": "%(episode_number)s", "episode": "%(title)s", "id": "[%(id)s]"
    }
    selected_parts = [key_map[key] for key in order if parts_cfg.get(key, False) and key in key_map]
    if parts_cfg.get("series"):
        return f"%(series,playlist_title)s/{' '.join(selected_parts)}.%(ext)s"
    else:
        return f"{' '.join(selected_parts)}.%(ext)s"

def canonicalize_config_parallel(config: Dict[str, Any]) -> int:
    def clamp(n: Any) -> int:
        try:
            val = int(float(n)); return max(PARALLEL_MIN, min(PARALLEL_MAX, val))
        except (ValueError, TypeError): return DEFAULT_PARALLEL
    if "max_concurrent_downloads" in config: return clamp(config["max_concurrent_downloads"])
    legacy_keys = ["max_parallel", "max_parallel_downloads", "parallel_downloads",
                   "concurrent_downloads", "max_concurrent", "concurrency"]
    for key in legacy_keys:
        if key in config: return clamp(config[key])
    for container_key in ["downloads", "download", "settings", "general", "app"]:
        if isinstance(config.get(container_key), dict):
            nested_dict = config[container_key]
            for key in ["max_parallel", "parallel", "concurrent", "max"]:
                if key in nested_dict: return clamp(nested_dict[key])
    return DEFAULT_PARALLEL

def get_startupinfo():
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    return None

def open_file_location(filepath: str):
    try:
        if sys.platform == "win32": subprocess.run(["explorer", "/select,", os.path.normpath(filepath)])
        elif sys.platform == "darwin": subprocess.run(["open", "-R", filepath])
        else: subprocess.run(["xdg-open", os.path.dirname(filepath)])
    except Exception: pass

def handle_exception(exc_type, exc_value, exc_traceback):
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_file = "TVerDownloader_crash.log"
    with open(log_file, "w", encoding="utf-8") as f: f.write(error_message)
    error_box = QMessageBox(); error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setWindowTitle("오류"); error_box.setText("치명적인 오류가 발생했습니다.")
    error_box.setInformativeText(f"오류 상세가 '{log_file}' 파일에 저장되었습니다.")
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok); error_box.exec()

def open_feedback_link(): webbrowser.open("https://github.com/deuxdoom/TVerDownloader/issues")
def open_developer_link(): webbrowser.open("https://www.youtube.com/@LE_SSERAFIM")