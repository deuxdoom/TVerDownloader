# src/history_store.py
# 목적: 다운로드 이력 파일(urlhistory.json) 로드/저장/조회
# 수정: 다운로드된 파일의 최종 경로(filepath)를 함께 저장하는 기능 추가

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Union, Optional

class HistoryStore:
    DEFAULT_BAK_DIR = Path("historybak")
    DEFAULT_KEEP = 30

    def __init__(self, path: str = "urlhistory.json",
                 backup_dir: Optional[Path] = None,
                 keep_backups: int = DEFAULT_KEEP):
        self.path = path
        self._mode = "dict"
        self._data: Union[List[dict], Dict[str, dict]] = {}
        self.backup_dir: Path = backup_dir or self.DEFAULT_BAK_DIR
        self.keep_backups: int = max(0, int(keep_backups))

    def load(self) -> bool:
        p = Path(self.path)
        if not p.exists():
            self._mode = "dict"
            self._data = {}
            return True
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                self._mode = "dict"
                self._data = obj
            elif isinstance(obj, list):
                # 레거시 list 형식을 dict 형식으로 변환하여 로드
                self._mode = "dict"
                self._data = {
                    item.get("url"): {
                        "title": item.get("title", ""),
                        "date": item.get("date", ""),
                        "filepath": item.get("filepath", "")
                    }
                    for item in obj if isinstance(item, dict) and item.get("url")
                }
            else:
                self._data = {}
            return True
        except (json.JSONDecodeError, IOError):
            self._data = {}
            return False

    def save(self) -> bool:
        try:
            target = Path(self.path)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            if target.exists():
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak_path = self.backup_dir / f"urlhistory_{ts}.bak.json"
                try:
                    bak_path.write_bytes(target.read_bytes())
                    self._prune_backups()
                except OSError: pass

            tmp_path = target.with_suffix(".tmp")
            # 항상 dict 형식으로 저장
            tmp_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(target)
            return True
        except Exception:
            return False

    def _prune_backups(self):
        if self.keep_backups <= 0: return
        try:
            files = sorted(self.backup_dir.glob("urlhistory_*.bak.json"), key=lambda p: p.stat().st_mtime)
            for f in files[:-self.keep_backups]:
                f.unlink(missing_ok=True)
        except OSError: pass

    def exists(self, url: str) -> bool:
        return (url or "").strip() in self._data

    def get_title(self, url: str) -> str:
        entry = self._data.get((url or "").strip(), {})
        return entry.get("title", "(제목 없음)") if isinstance(entry, dict) else ""

    def add(self, url: str, title: str, filepath: Optional[str] = None) -> None:
        url = (url or "").strip()
        if not url: return
        
        # dict 모드에서만 동작
        if not isinstance(self._data, dict): self._data = {}
        
        self._data[url] = {
            "title": title or "(제목 없음)",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filepath": filepath or ""
        }

    def remove(self, url: str) -> None:
        url = (url or "").strip()
        if url and isinstance(self._data, dict) and url in self._data:
            self._data.pop(url)

    def sorted_entries(self) -> List[Tuple[str, dict]]:
        if not isinstance(self._data, dict): return []
        
        # 날짜를 기준으로 내림차순 정렬
        return sorted(
            self._data.items(),
            key=lambda item: item[1].get("date", "") if isinstance(item[1], dict) else "",
            reverse=True
        )