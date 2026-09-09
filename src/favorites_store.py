from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Tuple, Iterable, List, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FavoritesStore:
    BAK_DIR_NAME = "favoritbak"
    DEFAULT_KEEP = 30
    """남겨 둘 백업 개수. HistoryStore와 같은 값이다.

    **자르지 않으면 끝없이 쌓인다** - touch_last_check가 시리즈마다 저장을 부르므로
    `모두 갱신` 한 번에 스무 개까지 늘어난다. 되돌아가 볼 것은 최근 몇 개뿐이다.
    """

    def __init__(self, path: str, keep_backups: int = DEFAULT_KEEP):
        self.path = path
        self._data: Dict[str, Dict[str, str]] = {}
        self.keep_backups: int = max(0, int(keep_backups))

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
        """저장 직전의 파일을 백업 폴더에 남기고 오래된 것을 정리한다."""
        if not os.path.exists(self.path):
            return
        base_dir = os.path.dirname(os.path.abspath(self.path))
        bak_dir = os.path.join(base_dir, self.BAK_DIR_NAME)
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
        self._prune_backups(bak_dir)

    def _prune_backups(self, bak_dir: str) -> None:
        """오래된 백업부터 지워 keep_backups개만 남긴다.

        실패를 삼키는 것은 정리가 저장을 막으면 안 되기 때문이다. 백업이 지워지지
        않는 것보다 즐겨찾기가 저장되지 않는 쪽이 훨씬 나쁘다.
        """
        if self.keep_backups <= 0:
            return
        try:
            names = [n for n in os.listdir(bak_dir)
                     if n.startswith("favorites_") and n.endswith(".bak.json")]
            paths = sorted((os.path.join(bak_dir, n) for n in names),
                           key=os.path.getmtime)
            for stale in paths[:-self.keep_backups]:
                os.remove(stale)
        except OSError:
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

    def touch_last_check(self, series_url: str, series_title: Optional[str] = None) -> bool:
        """마지막 확인 시각을 적는다. 목록에 없으면 아무것도 하지 않고 False.

        **없는 것을 새로 만들지 않는다.** 분석은 72화 시리즈에서 60초까지 걸리고 그동안
        사용자가 그 시리즈를 지울 수 있는데, 늦게 도착한 결과가 만들어 버리면 **지운 것이
        되살아난다.** 담는 일은 add() 한 곳에서만 한다.

        돌려주는 값은 '아직 유효한 요청인가'라는 뜻이다 - 부르는 쪽이 그 뒤의 일(신규 회차를
        대기열에 넣는 것)을 이어갈지 이 값으로 정한다.
        """
        u = (series_url or "").strip()
        if not u or u not in self._data:
            return False

        self._data[u]["last_check"] = _now_str()
        if series_title and self._data[u].get("title") != series_title:
            self._data[u]["title"] = series_title
        self.save()
        return True
