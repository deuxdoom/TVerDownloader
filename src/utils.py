# 파일명: src/utils.py
# 목적: 설정 저장/로드, 예외 핸들러, 파일 위치 열기, 간단 유틸

import json
import os
import sys
import traceback
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import QMessageBox

CONFIG_FILE = "downloader_config.json"

# 레거시: 구버전과 호환을 위해 남겨둠(현재는 HistoryStore 사용 권장)
HISTORY_FILE = Path("urlhistory.json")


def load_config():
    """설정 파일 로드(없으면 기본값). dict 병합으로 부분 업데이트 허용."""
    config = {
        "theme": "dark",  # 다크 고정
        "download_folder": "",
        "max_concurrent_downloads": 3,
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
        # ★ 즐겨찾기: 시작 시 자동 확인 여부
        "auto_check_favorites_on_start": True,
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict):
                        config.setdefault(k, {}).update(v)
                    else:
                        config[k] = v
            except json.JSONDecodeError:
                pass  # 손상 시 기본값 사용
    return config


def save_config(config: dict):
    """설정 파일 저장."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# 레거시 히스토리 유틸 (구버전 호환용) — 현재는 src/history_store.py 사용 권장
# ─────────────────────────────────────────────────────────────────────────────
def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history_dict = json.load(f)
                if not isinstance(history_dict, dict):
                    return []
                return [{"url": url, **data} for url, data in history_dict.items()]
            except json.JSONDecodeError:
                return []
    return []


def add_to_history(history, url, data):
    """레거시: 리스트 기반 히스토리 추가 후 파일엔 dict로 저장."""
    if not isinstance(data, dict):
        data = {"title": data}  # 예전 형식(title 문자열) 호환
    data.setdefault("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    data.setdefault("filepath", "")

    if not any(entry.get("url") == url for entry in history):
        history.append({"url": url, **data})

    history_dict = {entry["url"]: {k: v for k, v in entry.items() if k != "url"} for entry in history}
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_dict, f, indent=4, ensure_ascii=False)
    return True


def remove_from_history(url):
    """레거시: 파일 기반에서 URL 키 삭제."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_dict = json.load(f) or {}
            if isinstance(history_dict, dict) and url in history_dict:
                del history_dict[url]
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(history_dict, f, indent=4, ensure_ascii=False)
                return True
        except json.JSONDecodeError:
            return False
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 시스템 유틸
# ─────────────────────────────────────────────────────────────────────────────
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
        pass  # 실패해도 치명적 아님


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
    error_box.setInformativeText(
        f"오류 상세가 '{log_file}' 파일에 저장되었습니다.\n개발자에게 문의 시 이 파일을 함께 전달해주세요."
    )
    error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    error_box.exec()


# ─────────────────────────────────────────────────────────────────────────────
# 외부 링크
# ─────────────────────────────────────────────────────────────────────────────
def open_feedback_link():
    webbrowser.open("https://github.com/deuxdoom/TVerDownloader/issues")


def open_developer_link():
    webbrowser.open("https://www.youtube.com/@LE_SSERAFIM")
