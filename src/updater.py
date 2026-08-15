from __future__ import annotations
import re
import webbrowser

from src.utils import github_api_headers, is_rate_limited, rate_limit_message

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

def maybe_show_update(parent, current_version: str, log=print) -> None:
    """GitHub /releases/latest API를 호출하여 최신 태그를 확인하고, 새 버전이 있으면 안내창을 표시합니다.

    시작 시 한 번만 부르는 부가 기능이라 재시도하지 않는다. 한 번 실패하면
    다음 실행 때 다시 확인하면 된다.
    """
    try:
        import requests
    except ImportError:
        return

    API_URL = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
    RELEASE_PAGE_URL = "https://github.com/deuxdoom/TVerDownloader/releases/latest"
    headers = github_api_headers("TVerDownloader-UpdateCheck")

    try:
        response = requests.get(API_URL, headers=headers, timeout=10)
    except requests.exceptions.RequestException:
        return

    if is_rate_limited(response):
        log(f"[알림] 업데이트 확인을 건너뜁니다. {rate_limit_message(response)}")
        return

    if response.status_code != 200:
        return

    try:
        release_data = response.json()
    except ValueError:
        return

    latest_tag = release_data.get("tag_name") or release_data.get("name") or ""
    html_url = release_data.get("html_url") or RELEASE_PAGE_URL

    if not latest_tag or not _newer(current_version, latest_tag):
        return

    from PyQt6.QtWidgets import QMessageBox

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("새 버전 확인")

    text = f"새 버전 {latest_tag}이(가) 릴리스 되었습니다.\n지금 다운받으러 이동하시겠습니까?"
    msg_box.setText(text)

    go_btn = msg_box.addButton("이동", QMessageBox.ButtonRole.AcceptRole)
    msg_box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
    msg_box.setDefaultButton(go_btn)

    msg_box.exec()

    if msg_box.clickedButton() == go_btn:
        try:
            webbrowser.open(html_url)
        except Exception:
            pass
