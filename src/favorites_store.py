# src/favorites_store.py
# 수정:
# - 데이터 구조에 "title" 필드 추가
# - add: title을 빈 문자열로 초기화
# - load: title 필드를 로드 (없을 경우 빈 문자열)
# - touch_last_check: series_title을 선택적으로 받아 업데이트

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Tuple, Iterable, List, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FavoritesStore:
    def __init__(self, path: str, *, related_history_path: Optional[str] = None):
        self.path = path
        self.related_history_path = related_history_path
        self._data: Dict[str, Dict[str, str]] = {}

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            self._data = {}
            return

        out: Dict[str, Dict[str, str]] = {}
        if isinstance(raw, dict):
            for url, meta in raw.items():
                if not isinstance(url, str):
                    continue
                added = ""
                last = ""
                title = "" # ✅ title 변수
                if isinstance(meta, dict):
                    a = meta.get("added") or meta.get("added_at") or meta.get("created") or ""
                    l = meta.get("last_check") or meta.get("checked_at") or ""
                    t = meta.get("title", "") # ✅ title 로드
                    added = str(a) if isinstance(a, (str, int, float)) else ""
                    last = str(l) if isinstance(l, (str, int, float)) else ""
                    title = str(t) if isinstance(t, str) else ""
                # ✅ title 포함하여 저장
                out[url] = {"added": added or _now_str(), "last_check": last, "title": title}
        elif isinstance(raw, list):
            # (하위 호환성)
            for item in raw:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("href") or item.get("link")
                    if isinstance(url, str):
                        out[url] = {
                            "added": item.get("added") or _now_str(),
                            "last_check": item.get("last_check") or "",
                            "title": item.get("title", "") # ✅ title 로드
                        }
        self._data = out

    def _ensure_parent(self) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)

    def _backup_existing(self) -> None:
        if not os.path.exists(self.path):
            return
        base_dir = os.path.dirname(os.path.abspath(self.path))
        bak_dir = os.path.join(base_dir, "favoritbak")
        os.makedirs(bak_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"favorites_{ts}.bak.json"
        try:
            with open(self.path, "r", encoding="utf-8") as src, open(
                os.path.join(bak_dir, name), "w", encoding="utf-8"
            ) as dst:
                dst.write(src.read())
        except Exception:
            pass

    def save(self) -> None:
        self._ensure_parent()
        self._backup_existing()
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def add(self, series_url: str) -> None:
        u = (series_url or "").strip()
        if not u:
            return
        if u not in self._data:
            # ✅ title을 빈 문자열로 초기화
            self._data[u] = {"added": _now_str(), "last_check": "", "title": ""}
            self.save()

    def remove(self, series_url: str) -> None:
        u = (series_url or "").strip()
        if not u:
            return
        if u in self._data:
            self._data.pop(u, None)
            self.save()

    def exists(self, series_url: str) -> bool:
        return (series_url or "").strip() in self._data

    def list_series(self) -> List[str]:
        return list(self._data.keys())

    def sorted_entries(self) -> Iterable[Tuple[str, Dict[str, str]]]:
        def key(t: Tuple[str, Dict[str, str]]):
            url, meta = t
            return (meta.get("added") or "", url)
        return sorted(self._data.items(), key=key, reverse=False)

    # ✅ series_title 인자 추가
    def touch_last_check(self, series_url: str, series_title: Optional[str] = None) -> None:
        u = (series_url or "").strip()
        if not u:
            return
            
        now = _now_str()
        if u not in self._data:
            # 존재하지 않으면 자동으로 추가 후 기록
            self._data[u] = {"added": now, "last_check": now, "title": series_title or ""}
        else:
            # 존재하면 업데이트
            self._data[u]["last_check"] = now
            # ✅ 전달된 시리즈 제목이 있고, 기존 제목과 다를 경우에만 업데이트
            if series_title and self._data[u].get("title") != series_title:
                self._data[u]["title"] = series_title
        self.save()