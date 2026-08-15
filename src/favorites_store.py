from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Tuple, Iterable, List, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FavoritesStore:
    def __init__(self, path: str):
        self.path = path
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
                title = ""
                if isinstance(meta, dict):
                    a = meta.get("added") or meta.get("added_at") or meta.get("created") or ""
                    l = meta.get("last_check") or meta.get("checked_at") or ""
                    t = meta.get("title", "")
                    added = str(a) if isinstance(a, (str, int, float)) else ""
                    last = str(l) if isinstance(l, (str, int, float)) else ""
                    title = str(t) if isinstance(t, str) else ""
                out[url] = {"added": added or _now_str(), "last_check": last, "title": title}
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("href") or item.get("link")
                    if isinstance(url, str):
                        out[url] = {
                            "added": item.get("added") or _now_str(),
                            "last_check": item.get("last_check") or "",
                            "title": item.get("title", ""),
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

    def touch_last_check(self, series_url: str, series_title: Optional[str] = None) -> None:
        u = (series_url or "").strip()
        if not u:
            return

        now = _now_str()
        if u not in self._data:
            self._data[u] = {"added": now, "last_check": now, "title": series_title or ""}
        else:
            self._data[u]["last_check"] = now
            if series_title and self._data[u].get("title") != series_title:
                self._data[u]["title"] = series_title
        self.save()
