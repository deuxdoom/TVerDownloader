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
                history_dict = json.load(f)
                if not isinstance(history_dict, dict):
                    return []
                return [{"url": url, **data} for url, data in history_dict.items()]
            except json.JSONDecodeError:
                return []
    return []

def add_to_history(history, url, data):
    # history는 리스트, 새로운 항목 추가
    if not isinstance(data, dict):
        data = {"title": data}  # 이전 호환성을 위해 기본 title만 처리
    if "date" not in data:
        data["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "filepath" not in data:
        data["filepath"] = ""
    # 중복 체크 후 추가
    if not any(entry["url"] == url for entry in history):
        history.append({"url": url, **data})
    # 파일에 딕셔너리 형식으로 저장
    history_dict = {entry["url"]: {k: v for k, v in entry.items() if k != "url"} for entry in history}
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_dict, f, indent=4, ensure_ascii=False)
    return True

def remove_from_history(url):
    history_path = HISTORY_FILE
    if history_path.exists():
        with open(history_path, 'r', encoding='utf-8') as f:
            try:
                history_dict = json.load(f)
                if url in history_dict:
                    del history_dict[url]
                    with open(history_path, 'w', encoding='utf-8') as f:
                        json.dump(history_dict, f, indent=4, ensure_ascii=False)
                    return True
            except json.JSONDecodeError:
                return False
    return False

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