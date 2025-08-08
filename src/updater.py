# 파일명: src/updater.py
from __future__ import annotations
import re
import webbrowser

def _norm(tag: str) -> tuple[int,int,int]:
    if not tag: return (0,0,0)
    t = tag.strip()
    if t[:1].lower() == "v": t = t[1:]
    t = t.split('-',1)[0].split('+',1)[0]
    nums = re.findall(r'\d+', t)[:3]
    parts = [int(x) for x in nums] + [0]*(3-len(nums))
    return tuple(parts[:3])

def _newer(cur: str, latest: str) -> bool:
    return _norm(latest) > _norm(cur)

def maybe_show_update(parent, current_version: str) -> None:
    """GitHub /releases/latest → 최신 태그 비교 후 안내. 실패 시 조용히 리턴."""
    try:
        import requests
    except Exception:
        return

    API = "https://api.github.com/repos/deuxdoom/TVerDownloader/releases/latest"
    PAGE = "https://github.com/deuxdoom/TVerDownloader/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TVerDownloader (update-check)"}

    latest_tag, html_url, body = "", PAGE, ""
    try:
        r = requests.get(API, headers=headers, timeout=10); r.raise_for_status()
        js = r.json()
        latest_tag = js.get("tag_name") or js.get("name") or ""
        html_url = js.get("html_url") or PAGE
        body = js.get("body") or ""
    except Exception:
        try:
            r = requests.get(PAGE, headers=headers, timeout=10); r.raise_for_status()
            m = re.search(r'>\s*v?(\d+\.\d+\.\d+)\s*<', r.text)
            latest_tag = f"v{m.group(1)}" if m else ""
            html_url = PAGE
            body = ""
        except Exception:
            return

    if not latest_tag or not _newer(current_version, latest_tag):
        return

    from PyQt6.QtWidgets import QMessageBox
    msg = QMessageBox(parent)
    msg.setWindowTitle("새 버전 확인")
    text = f"새 버전 {latest_tag} 이(가) 공개되었습니다.\n지금 릴리스 페이지로 이동할까요?"
    if body:
        preview = body.strip().splitlines()[0][:140]
        if preview:
            text += f"\n\n- 릴리스 노트: {preview}"
    msg.setText(text)
    go_btn = msg.addButton("이동", QMessageBox.ButtonRole.AcceptRole)
    later_btn = msg.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(go_btn)
    msg.exec()
    if msg.clickedButton() == go_btn:
        try: webbrowser.open(html_url)
        except Exception: pass
