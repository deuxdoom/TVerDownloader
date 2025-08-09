# -*- coding: utf-8 -*-
"""
파일명: src/history_store.py

역할
- 다운로드 이력 파일(urlhistory.json) 로드/저장/조회
- 레거시 포맷(list형)과 신형 포맷(dict형) 모두 호환
- 저장 시 백업(.bak)을 프로젝트 루트가 아닌 "./historybak" 폴더에 생성
  · 파일명: urlhistory_YYYYmmdd_HHMMSS.bak.json
  · 백업 보존 개수 제한(기본 30개)로 과도한 누적 방지

공개 API (MainWindow 등에서 사용)
- load() -> bool
- save() -> bool
- add(url: str, title: str, date: str | None = None) -> None
- remove(url: str) -> None
- exists(url: str) -> bool
- get_title(url: str) -> str
- iter_entries() -> Iterable[tuple[str, dict]]
- sorted_entries() -> list[tuple[str, dict]]

주의
- 저장 포맷은 "로드된 포맷을 유지"한다. (list로 로드되면 list로 저장, dict면 dict로 저장)
- 새로 생성되는 경우 기본 포맷은 dict.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Union, Optional


HistoryType = Union[List[dict], Dict[str, dict]]


class HistoryStore:
    """urlhistory.json을 list/dict 양식 모두 호환해 관리."""
    # 백업 폴더 및 보존 개수 기본값
    DEFAULT_BAK_DIR = Path("historybak")
    DEFAULT_KEEP = 30

    def __init__(self, path: str = "urlhistory.json",
                 backup_dir: Optional[Path] = None,
                 keep_backups: int = DEFAULT_KEEP):
        self.path = path
        self._mode = "dict"   # "list" | "dict"
        self._data: HistoryType = {}
        self.backup_dir: Path = backup_dir or self.DEFAULT_BAK_DIR
        self.keep_backups: int = max(0, int(keep_backups))

    # ──────────────────────────────────────────────────────────────────────
    # 로드/세이브
    # ──────────────────────────────────────────────────────────────────────
    def load(self) -> bool:
        """urlhistory.json을 로드. 포맷 자동 감지."""
        p = Path(self.path)
        if not p.exists():
            # 파일 없으면 빈 dict 모드로 시작
            self._mode = "dict"
            self._data = {}
            return True

        try:
            raw = p.read_text(encoding="utf-8")
            obj = json.loads(raw)

            if isinstance(obj, list):
                # list 모드(레거시)
                self._mode = "list"
                # 정규화: 필수 키 보정
                norm: List[dict] = []
                for e in obj:
                    if not isinstance(e, dict):
                        continue
                    url = str(e.get("url") or "").strip()
                    if not url:
                        continue
                    title = str(e.get("title") or "(제목 없음)")
                    date = str(e.get("date") or "")
                    norm.append({"url": url, "title": title, "date": date})
                self._data = norm

            elif isinstance(obj, dict):
                # dict 모드(신형)
                self._mode = "dict"
                # 정규화
                norm_d: Dict[str, dict] = {}
                for url, meta in obj.items():
                    if not isinstance(url, str) or not isinstance(meta, dict):
                        continue
                    url_s = url.strip()
                    if not url_s:
                        continue
                    title = str(meta.get("title") or "(제목 없음)")
                    date = str(meta.get("date") or "")
                    norm_d[url_s] = {"title": title, "date": date}
                self._data = norm_d
            else:
                # 알 수 없는 구조 → 안전하게 초기화
                self._mode = "dict"
                self._data = {}

            return True

        except Exception:
            # 파싱 에러 시에도 초기화하여 앱이 계속 동작하도록 함
            self._mode = "dict"
            self._data = {}
            return False

    def save(self) -> bool:
        """
        현재 상태를 파일에 저장.
        저장 직전, 기존 파일이 존재하면 ./historybak/ 아래에 백업 파일 생성.
        - 백업 파일명: urlhistory_YYYYmmdd_HHMMSS.bak.json
        - 보존 개수 self.keep_backups 보다 많으면 오래된 것부터 삭제
        """
        try:
            target = Path(self.path)

            # 1) 백업 디렉터리 준비
            try:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                # 백업 폴더 생성 실패해도 저장은 진행
                pass

            # 2) 기존 파일 백업
            if target.exists() and self.backup_dir.exists():
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak_name = f"urlhistory_{ts}.bak.json"
                bak_path = self.backup_dir / bak_name
                try:
                    bak_path.write_bytes(target.read_bytes())
                except Exception:
                    # 백업 실패해도 저장은 진행
                    pass
                else:
                    # 백업 개수 관리
                    self._prune_backups()

            # 3) 안전 저장(임시 파일 → 교체)
            tmp_path = target.with_suffix(".tmp")
            if self._mode == "list":
                payload = self._as_list()
            else:
                payload = self._as_dict()

            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(target)
            return True

        except Exception:
            return False

    def _prune_backups(self):
        """보존 개수 초과 시 오래된 백업부터 삭제."""
        if self.keep_backups <= 0:
            return
        try:
            files = sorted(
                [p for p in self.backup_dir.glob("urlhistory_*.bak.json") if p.is_file()],
                key=lambda p: p.stat().st_mtime
            )
            excess = len(files) - self.keep_backups
            for i in range(excess):
                try:
                    files[i].unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # 조회/조작
    # ──────────────────────────────────────────────────────────────────────
    def exists(self, url: str) -> bool:
        url = (url or "").strip()
        if not url:
            return False
        if self._mode == "list":
            for e in self._data:  # type: ignore[list-item]
                if isinstance(e, dict) and e.get("url") == url:
                    return True
            return False
        # dict 모드
        return url in self._data  # type: ignore[operator]

    def get_title(self, url: str) -> str:
        url = (url or "").strip()
        if not url:
            return "(제목 없음)"
        if self._mode == "list":
            for e in self._data:  # type: ignore[list-item]
                if isinstance(e, dict) and e.get("url") == url:
                    return str(e.get("title") or "(제목 없음)")
            return "(제목 없음)"
        return str(self._data.get(url, {}).get("title") or "(제목 없음)")  # type: ignore[index]

    def add(self, url: str, title: str, date: Optional[str] = None) -> None:
        """이력에 추가(중복 시 갱신)."""
        url = (url or "").strip()
        if not url:
            return
        if not date:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self._mode == "list":
            # 중복 제거 후 맨 앞에 삽입
            new_list: List[dict] = []
            found = False
            for e in self._data:  # type: ignore[list-item]
                if isinstance(e, dict) and e.get("url") == url:
                    found = True
                    continue
                new_list.append(e)
            new_list.insert(0, {"url": url, "title": title or "(제목 없음)", "date": date})
            self._data = new_list
            return

        # dict 모드
        d: Dict[str, dict] = dict(self._data)  # type: ignore[arg-type]
        d[url] = {"title": title or "(제목 없음)", "date": date}
        self._data = d

    def remove(self, url: str) -> None:
        """이력에서 제거."""
        url = (url or "").strip()
        if not url:
            return
        if self._mode == "list":
            self._data = [e for e in self._data  # type: ignore[assignment]
                          if not (isinstance(e, dict) and e.get("url") == url)]
            return

        d: Dict[str, dict] = dict(self._data)  # type: ignore[arg-type]
        if url in d:
            d.pop(url, None)
            self._data = d

    # ──────────────────────────────────────────────────────────────────────
    # 뷰 바인딩 유틸
    # ──────────────────────────────────────────────────────────────────────
    def iter_entries(self) -> Iterable[Tuple[str, dict]]:
        """
        (url, meta) 형태로 순회. list/dict를 통일해 제공.
        meta: {"title": str, "date": str}
        """
        if self._mode == "list":
            for e in self._data:  # type: ignore[list-item]
                if isinstance(e, dict):
                    yield str(e.get("url") or ""), {
                        "title": str(e.get("title") or "(제목 없음)"),
                        "date": str(e.get("date") or "")
                    }
        else:
            for url, meta in self._data.items():  # type: ignore[union-attr]
                url_s = str(url)
                if not isinstance(meta, dict):
                    yield url_s, {"title": "(제목 없음)", "date": ""}
                else:
                    yield url_s, {
                        "title": str(meta.get("title") or "(제목 없음)"),
                        "date": str(meta.get("date") or "")
                    }

    def sorted_entries(self) -> List[Tuple[str, dict]]:
        """date 역순 정렬 목록."""
        return sorted(self.iter_entries(), key=lambda kv: kv[1].get("date", ""), reverse=True)

    # ──────────────────────────────────────────────────────────────────────
    # 내부 저장 형식화
    # ──────────────────────────────────────────────────────────────────────
    def _as_list(self) -> List[dict]:
        if self._mode == "list":
            # 이미 list면 그대로(정렬은 date 역순으로 정리)
            return [{"url": u, "title": m.get("title", "(제목 없음)"), "date": m.get("date", "")}
                    for u, m in self.sorted_entries()]
        # dict → list 변환
        return [{"url": u, "title": m.get("title", "(제목 없음)"), "date": m.get("date", "")}
                for u, m in self.sorted_entries()]

    def _as_dict(self) -> Dict[str, dict]:
        if self._mode == "dict":
            # 정렬 유지하며 dict로 직렬화
            return {u: {"title": m.get("title", "(제목 없음)"), "date": m.get("date", "")}
                    for u, m in self.sorted_entries()}
        # list → dict 변환
        out: Dict[str, dict] = {}
        for u, m in self.sorted_entries():
            out[u] = {"title": m.get("title", "(제목 없음)"), "date": m.get("date", "")}
        return out
