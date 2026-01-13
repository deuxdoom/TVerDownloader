# src/history_store.py

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional
from concurrent.futures import ThreadPoolExecutor

class HistoryStore:
    DEFAULT_BAK_DIR = Path("historybak")
    DEFAULT_KEEP = 30

    def __init__(self, path: str = "urlhistory.json",
                 backup_dir: Optional[Path] = None,
                 keep_backups: int = DEFAULT_KEEP):
        self.path = path
        self._data: Dict[str, dict] = {}
        self.backup_dir: Path = backup_dir or self.DEFAULT_BAK_DIR
        self.keep_backups: int = max(0, int(keep_backups))
        # UI 블로킹 방지를 위한 단일 스레드 실행기
        self._executor = ThreadPoolExecutor(max_workers=1)

    def load(self) -> bool:
        p = Path(self.path)
        if not p.exists():
            self._data = {}
            return True
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                self._data = obj
            elif isinstance(obj, list):
                self._data = {
                    item.get("url"): {
                        "title": item.get("title", ""), "date": item.get("date", ""),
                        "filepath": item.get("filepath", ""), "series_id": item.get("series_id"),
                        "thumbnail_url": item.get("thumbnail_url")
                    } for item in obj if isinstance(item, dict) and item.get("url")
                }
            else: self._data = {}
            return True
        except (json.JSONDecodeError, IOError):
            self._data = {}; return False

    def save(self) -> None:
        """비동기로 저장을 수행하여 UI 블로킹을 방지합니다."""
        # 현재 데이터의 스냅샷을 만들어 백그라운드 스레드로 전달
        data_snapshot = self._data.copy()
        self._executor.submit(self._save_sync, data_snapshot)

    def _save_sync(self, data: Dict[str, dict]) -> bool:
        """실제 디스크 쓰기 작업 (백그라운드에서 실행됨)"""
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
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(target)
            return True
        except Exception: return False

    def _prune_backups(self):
        if self.keep_backups <= 0: return
        try:
            files = sorted(self.backup_dir.glob("urlhistory_*.bak.json"), key=lambda p: p.stat().st_mtime)
            for f in files[:-self.keep_backups]: f.unlink(missing_ok=True)
        except OSError: pass

    def exists(self, url: str) -> bool:
        return (url or "").strip() in self._data

    def get_title(self, url: str) -> str:
        entry = self._data.get((url or "").strip(), {})
        return entry.get("title", "(제목 없음)")

    def add(self, url: str, title: str, filepath: Optional[str] = None, 
            series_id: Optional[str] = None, thumbnail_url: Optional[str] = None):
        """기록에 항목을 추가합니다. series_id와 thumbnail_url을 선택적으로 저장합니다."""
        url = (url or "").strip()
        if not url: return
        
        self._data[url] = {
            "title": title or "(제목 없음)",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filepath": filepath or "",
            "series_id": series_id,
            "thumbnail_url": thumbnail_url
        }

    def remove(self, url: str) -> None:
        url = (url or "").strip()
        if url and url in self._data: self._data.pop(url)

    def sorted_entries(self) -> List[Tuple[str, dict]]:
        return sorted(self._data.items(), key=lambda item: item[1].get("date", ""), reverse=True)