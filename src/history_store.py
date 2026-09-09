from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

from src.utils import canonical_url

def _key(url: str) -> str:
    """기록을 찾고 담을 때 쓰는 키. TVer 주소는 쿼리를 뗀 형태로 모은다.

    같은 회차라도 공유 경로에 따라 `?utm_source=...`가 붙어 오는데, 글자 그대로 견주면
    이미 받은 것을 또 받는다. **utils는 위에서 가져와도 된다** - 이 모듈로 되돌아오는
    고리가 없다(늦춰 가져오는 것은 화면 문구를 다루는 i18n뿐이다).
    """
    return canonical_url(url)


LEGACY_NO_TITLE = ("", "(제목 없음)")
"""제목이 없다는 뜻으로 파일에 남아 있을 수 있는 값들. **화면 문구가 아니라 자료값이다.**

지금은 빈 문자열로 적고 보여 줄 때 번역하지만, 4.0.0 전에 받은 기록에는 한국어 문구가
그대로 저장돼 있다. 그 줄까지 알아봐야 언어를 바꾼 뒤에도 한국어가 섞여 나오지 않는다.
"""


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
        self._executor = ThreadPoolExecutor(max_workers=1)

    def load(self) -> bool:
        p = Path(self.path)
        if not p.exists():
            self._data = {}
            return True
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                self._data = self._merge_by_key(obj)
            elif isinstance(obj, list):
                self._data = self._merge_by_key({
                    item.get("url"): {
                        "title": item.get("title", ""), "date": item.get("date", ""),
                        "filepath": item.get("filepath", ""), "series_id": item.get("series_id"),
                        "thumbnail_url": item.get("thumbnail_url")
                    } for item in obj if isinstance(item, dict) and item.get("url")
                })
            else: self._data = {}
            return True
        except (json.JSONDecodeError, IOError):
            self._data = {}; return False

    @staticmethod
    def _merge_by_key(raw: Dict[str, dict]) -> Dict[str, dict]:
        """읽어 들인 것을 같은 회차끼리 한 키로 모은다. 겹치면 날짜가 최신인 것을 남긴다.

        **담는 쪽만 다듬으면 옛 기록과 어긋난다.** 4.1.0 전에는 주소를 글자 그대로 담아
        같은 회차가 `?utm_source=...` 유무로 두 줄 남을 수 있었는데, 읽을 때 모으지 않으면
        새 코드가 찾는 키와 맞지 않아 **이미 받은 것을 다시 받고 파일 경로도 못 찾는다.**
        최신을 남기는 것은 그쪽에 지금 쓰는 파일 경로가 들어 있어서다.

        값이 사전이 아닌 줄은 버린다 - 손으로 고친 파일에서 `null`이 들어오면 그 뒤의
        모든 조회가 AttributeError로 넘어진다.
        """
        merged: Dict[str, dict] = {}
        for url, entry in raw.items():
            key = _key(url if isinstance(url, str) else "")
            if not key or not isinstance(entry, dict):
                continue
            kept = merged.get(key)
            if kept is None or entry.get("date", "") >= kept.get("date", ""):
                merged[key] = entry
        return merged

    def save(self) -> None:
        """비동기로 저장한다. 디스크 쓰기에 UI가 멈추지 않게 하려는 것."""
        data_snapshot = self._data.copy()
        self._executor.submit(self._save_sync, data_snapshot)

    def _save_sync(self, data: Dict[str, dict]) -> bool:
        """실제 디스크 쓰기. 백그라운드 스레드에서 돈다."""
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
        return _key(url) in self._data

    def get_title(self, url: str) -> str:
        from src.i18n import t
        entry = self._data.get(_key(url), {})
        stored = entry.get("title", "")
        return t("card.title_missing") if stored in LEGACY_NO_TITLE else stored

    def get_filepath(self, url: str) -> str:
        entry = self._data.get(_key(url), {})
        return entry.get("filepath", "")

    def add(self, url: str, title: str, filepath: Optional[str] = None,
            series_id: Optional[str] = None, thumbnail_url: Optional[str] = None):
        """기록에 항목을 더한다. series_id·thumbnail_url은 있으면 함께 남긴다."""
        url = _key(url)
        if not url: return

        self._data[url] = {
            "title": title or "",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filepath": filepath or "",
            "series_id": series_id,
            "thumbnail_url": thumbnail_url
        }

    def remove(self, url: str) -> None:
        """기록 하나를 뺀다. 찾는 키는 담을 때와 같아야 한다 - 다르면 지워지지 않는다."""
        key = _key(url)
        if key and key in self._data: self._data.pop(key)

    def sorted_entries(self) -> List[Tuple[str, dict]]:
        return sorted(self._data.items(), key=lambda item: item[1].get("date", ""), reverse=True)
