# 파일명: src/favorites_store.py
# 즐겨찾기(시리즈 URL) 저장/불러오기 관리

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


class FavoritesStore:
    """favorites.json 에 시리즈 URL을 저장/관리한다.
    구조:
    {
      "https://tver.jp/series/xxxx": {
        "added": "YYYY-mm-dd HH:MM:SS",
        "last_check": "YYYY-mm-dd HH:MM:SS"
      },
      ...
    }
    * known 에피소드 목록은 저장하지 않는다(단순화).
      자동 다운로드 대상을 '기록(history)' 기준으로 판단한다.
    """
    def __init__(self, path: str = "favorites.json"):
        self.path = Path(path)
        self._data: Dict[str, Dict[str, Any]] = {}

    # ---------- 파일 I/O ----------
    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        self._data = raw
            except Exception:
                self._data = {}

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ---------- CRUD ----------
    def list_series(self) -> List[str]:
        return list(self._data.keys())

    def exists(self, series_url: str) -> bool:
        return series_url in self._data

    def add(self, series_url: str) -> None:
        if series_url not in self._data:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._data[series_url] = {"added": now, "last_check": ""}
            self.save()

    def remove(self, series_url: str) -> None:
        if series_url in self._data:
            del self._data[series_url]
            self.save()

    def touch_last_check(self, series_url: str) -> None:
        if series_url in self._data:
            self._data[series_url]["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()

    # ---------- 정렬/표시용 ----------
    def sorted_entries(self) -> List[tuple[str, dict]]:
        # 최근 추가 순으로
        def key_fn(item):
            meta = item[1] or {}
            return meta.get("added", "")
        return sorted(self._data.items(), key=key_fn, reverse=True)
    
    # ---------- TVer 즐겨찾기 관련 ----------
    def add_many(self, series_urls: list[str]) -> int:
        """여러 시리즈 URL 추가. 신규 추가 개수 반환."""
        count = 0
        for u in series_urls:
            if u and u not in self._data:
                self.add(u)
                count += 1
        if count:
            self.save()
        return count    
