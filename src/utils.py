# src/utils.py

import json
import os
import sys
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QMessageBox
from src.icon import get_app_icon  # icon.py에서 get_app_icon 임포트

CONFIG_FILE = "downloader_config.json"
HISTORY_FILE = Path("urlhistory.json")

def load_config():
    config = {
        "theme": "light",
        "download_folder": "",
        "max_concurrent_downloads": 3,
        "filename_parts": {
            "series": True, "upload_date": True, "episode_number": True,
            "episode": True, "id": True
        },
        "post_action": "None",
        "quality": "bv*+ba/b"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                loaded_config = json.load(f)
                for key, value in loaded_config.items():
                    if isinstance(value, dict):
                        config.setdefault(key, {}).update(value)
                    else:
                        config[key] = value
            except json.JSONDecodeError:
                pass  # 기본 설정 사용
    return config

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def add_to_history(history, url, title):
    history[url] = {
        "title": title,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def get_startupinfo():
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    return None

def open_file_location(filepath):
    try:
        if sys.platform == 'win32':
            subprocess.run(['explorer', '/select,', os.path.normpath(filepath)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', filepath])
        else:
            subprocess.run(['xdg-open', os.path.dirname(filepath)])
    except Exception as e:
        pass  # 오류 무시 또는 로그

def handle_exception(exc_type, exc_value, exc_traceback):
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_file = "TVerDownloader_crash.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(error_message)
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setText("치명적인 오류가 발생했습니다.")
    error_box.setInformativeText(f"오류의 원인이 '{log_file}' 파일에 저장되었습니다. 개발자에게 문의 시 이 파일을 함께 전달해주세요.")
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    error_box.exec()

def open_feedback_link():
    webbrowser.open('https://github.com/deuxdoom/TVerDownloader/issues')

def open_developer_link():
    webbrowser.open('https://www.youtube.com/@LE_SSERAFIM')
