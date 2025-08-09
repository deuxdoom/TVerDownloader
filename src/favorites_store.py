# -*- coding: utf-8 -*-
# 즐겨찾기(시리즈 URL) 저장/로딩/정렬/백업 관리
# - 파일 포맷: { "<series_url>": { "added": "YYYY-MM-DD HH:MM:SS", "last_check": "YYYY-MM-DD HH:MM:SS" | "" } }
# - 백업: 저장 시 기존 파일을 ./favoritbak/ 아래에 타임스탬프로 보관
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

    # ---------- I/O ----------
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

        # 허용 포맷: dict(url -> meta)만 정식 지원. 그 외는 best-effort로 정규화
        out: Dict[str, Dict[str, str]] = {}
        if isinstance(raw, dict):
            for url, meta in raw.items():
                if not isinstance(url, str):
                    continue
                added = ""
                last = ""
                if isinstance(meta, dict):
                    a = meta.get("added") or meta.get("added_at") or meta.get("created") or ""
                    l = meta.get("last_check") or meta.get("checked_at") or ""
                    added = str(a) if isinstance(a, (str, int, float)) else ""
                    last = str(l) if isinstance(l, (str, int, float)) else ""
                out[url] = {"added": added or _now_str(), "last_check": last}
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("href") or item.get("link")
                    if isinstance(url, str):
                        out[url] = {
                            "added": item.get("added") or _now_str(),
                            "last_check": item.get("last_check") or "",
                        }
        self._data = out

    def _ensure_parent(self) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)

    def _backup_existing(self) -> None:
        """기존 파일을 ./favoritbak/ 밑으로 백업."""
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
            # 백업 실패는 저장을 막지 않는다
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
            # tmp가 남아있으면 정리
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    # ---------- 조작 ----------
    def add(self, series_url: str) -> None:
        u = (series_url or "").strip()
        if not u:
            return
        if u not in self._data:
            self._data[u] = {"added": _now_str(), "last_check": ""}
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
        # added 내림차순 → url 오름차순
        def key(t: Tuple[str, Dict[str, str]]):
            url, meta = t
            return (meta.get("added") or "", url)

        return sorted(self._data.items(), key=key, reverse=False)

    def touch_last_check(self, series_url: str) -> None:
        """해당 시리즈의 마지막 확인 시각을 now로 기록하고 저장."""
        u = (series_url or "").strip()
        if not u:
            return
        if u not in self._data:
            # 존재하지 않으면 자동으로 추가 후 기록
            self._data[u] = {"added": _now_str(), "last_check": _now_str()}
        else:
            self._data[u]["last_check"] = _now_str()
        self.save()
