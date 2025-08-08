# 파일명: src/history_store.py
from __future__ import annotations
import json
from datetime import datetime
from typing import Dict, List, Tuple, Iterable, Union

HistoryType = Union[List[dict], Dict[str, dict]]

class HistoryStore:
    """urlhistory.json을 list/dict 양식 모두 호환해 관리"""
    def __init__(self, path: str = "urlhistory.json"):
        self.path = path
        self._mode = "dict"   # "list" | "dict"
        self._data: HistoryType = {}

    @property
    def mode(self) -> str:
        return self._mode

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        self._mode = "dict" if isinstance(raw, dict) else "list"
        self._data = raw if raw else ([] if self._mode == "list" else {})

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)

    # ========== 조회 ==========
    def exists(self, url: str) -> bool:
        if self._mode == "list":
            return any(isinstance(e, dict) and e.get("url") == url for e in self._data)  # type: ignore
        return url in self._data  # type: ignore

    def get_title(self, url: str) -> str:
        if self._mode == "list":
            for e in self._data:  # type: ignore
                if isinstance(e, dict) and e.get("url") == url:
                    return e.get("title", "(제목 없음)")
            return "(제목 없음)"
        return self._data.get(url, {}).get("title", "(제목 없음)")  # type: ignore

    # ========== 변경 ==========
    def add(self, url: str, title: str, date: str | None = None) -> None:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self._mode == "list":
            self._data = [e for e in self._data if not (isinstance(e, dict) and e.get("url") == url)]  # type: ignore
            self._data.insert(0, {"url": url, "title": title, "date": date})  # type: ignore
        else:
            self._data[url] = {"title": title, "date": date}  # type: ignore
        self.save()

    def remove(self, url: str) -> None:
        if self._mode == "list":
            self._data = [e for e in self._data if not (isinstance(e, dict) and e.get("url") == url)]  # type: ignore
        else:
            self._data.pop(url, None)  # type: ignore
        self.save()

    # ========== 뷰 바인딩 ==========
    def iter_entries(self) -> Iterable[Tuple[str, dict]]:
        """(url, meta) 형태로 순회. list/dict를 통일해 제공."""
        if self._mode == "list":
            for e in self._data:  # type: ignore
                if isinstance(e, dict):
                    yield e.get("url", ""), {"title": e.get("title", "(제목 없음)"), "date": e.get("date", "")}
        else:
            for url, meta in self._data.items():  # type: ignore
                yield url, meta

    def sorted_entries(self) -> List[Tuple[str, dict]]:
        return sorted(self.iter_entries(), key=lambda kv: kv[1].get("date", ""), reverse=True)
