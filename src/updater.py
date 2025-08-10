# src/updater.py
# 수정: 업데이트 안내 메시지 박스의 텍스트를 수정하고, 릴리스 노트 미리보기 기능 제거

from __future__ import annotations
import re
import webbrowser

def _norm(tag: str) -> tuple[int,int,int]:
    """버전 태그를 비교 가능한 튜플로 변환합니다. (예: 'v2.3.1' -> (2, 3, 1))"""
    if not tag: return (0,0,0)
    t = tag.strip()
    if t.lower().startswith("v"): t = t[1:]
    t = t.split('-',1)[0].split('+',1)[0]
    nums = re.findall(r'\d+', t)[:3]
    parts = [int(x) for x in nums] + [0]*(3-len(nums))
    return tuple(parts[:3])

def _newer(cur: str, latest: str) -> bool:
    """최신 버전 태그가 현재 버전보다 높은지 비교합니다."""
    return _norm(latest) > _norm(cur)

def maybe_show_update(parent, current_version: str) -> None:
    """GitHub /releases/latest API를 호출하여 최신 태그를 확인하고, 새 버전이 있으면 안내창을 표시합니다."""
    try:
        import requests
    except ImportError:
        # requests 모듈이 없는 환경에서는 업데이트 확인을 건너뜁니다.
        return

    API_URL = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
    RELEASE_PAGE_URL = "https://github.com/deuxdoom/TVerDownloader/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TVerDownloader-UpdateCheck"}

    latest_tag = ""
    html_url = RELEASE_PAGE_URL
    
    try:
        # GitHub API를 통해 최신 릴리스 정보 요청
        response = requests.get(API_URL, headers=headers, timeout=10)
        response.raise_for_status()
        release_data = response.json()
        latest_tag = release_data.get("tag_name") or release_data.get("name") or ""
        html_url = release_data.get("html_url") or RELEASE_PAGE_URL
    except requests.exceptions.RequestException:
        # API 호출 실패 시 조용히 종료
        return

    # 새 버전이 없으면 아무 작업도 하지 않음
    if not latest_tag or not _newer(current_version, latest_tag):
        return

    # PyQt6.QtWidgets는 UI 스레드에서만 import하는 것이 안전하므로 함수 내에서 import
    from PyQt6.QtWidgets import QMessageBox
    
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("새 버전 확인")
    
    # 요청하신 문구로 수정
    text = f"새 버전 {latest_tag}이(가) 릴리스 되었습니다.\n지금 다운받으러 이동하시겠습니까?"
    msg_box.setText(text)
    
    go_btn = msg_box.addButton("이동", QMessageBox.ButtonRole.AcceptRole)
    later_btn = msg_box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
    msg_box.setDefaultButton(go_btn)
    
    msg_box.exec()
    
    if msg_box.clickedButton() == go_btn:
        try:
            webbrowser.open(html_url)
        except Exception:
            pass # 브라우저 열기 실패는 치명적인 오류가 아니므로 무시