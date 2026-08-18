"""아직 받지 못한 대기열을 파일 하나에 남겨 두는 곳.

**대기열이 메모리에만 있으면 앱을 끄는 순간 조용히 사라진다.** 카드까지 함께
없어져서, 다음에 켰을 때 무엇을 걸어 두었는지 알 방법이 없다. 자동 업데이트가
앱을 껐다 켜고(3.3.0), 미리 묻기가 긴 대기열을 쓸 만하게 만든(3.4.0) 뒤로는
잃는 것이 그만큼 커졌다.

**롤링 백업을 두지 않는 것이 HistoryStore와 다른 점이다.** 받은 기록은 한 번
잃으면 되찾을 수 없는 자산이라 30벌을 굴리지만, 이쪽은 대기열이 바뀔 때마다 —
하나 넣을 때, 하나 시작할 때, 하나 끝날 때마다 — 다시 쓰인다. 50개를 넣는 한
번의 조작만으로 백업이 50벌 쌓이고 그중 어느 것도 다시 볼 일이 없다.

**쓰기는 동기다.** 마지막 한 번이 앱을 끝내기 직전(stop_all)에 일어나는데,
다른 스레드에 맡기면 그 쓰기가 끝나기 전에 프로세스가 사라진다. 남길 것이 몇
KB뿐이라 그 자리에서 써도 눈에 띄지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _text(value: Any) -> str:
    """글이 아닌 것이 들어 있으면 빈 글로 본다."""
    return value if isinstance(value, str) else ""


class QueueStore:
    """대기열에 남은 항목을 담고, 파일과 주고받는다."""

    DEFAULT_PATH = "queue.json"

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._items: List[Dict[str, str]] = []

    def load(self) -> bool:
        """파일을 읽는다. 읽지 못하면 빈 채로 열되 실패를 알린다.

        없는 파일과 깨진 파일을 가른다. 없는 것은 대기열이 비어 있었다는 뜻이라
        정상이고, 깨진 것은 부르는 쪽이 로그에 남길 만한 일이다.
        """
        target = Path(self.path)
        if not target.exists():
            self._items = []
            return True
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            self._items = []
            return False
        self._items = self._clean(raw)
        return True

    @staticmethod
    def _clean(raw: Any) -> List[Dict[str, str]]:
        """쓸 수 있는 항목만 차례를 지켜 걸러 낸다.

        **차례가 곧 대기열 차례라 정렬하지 않는다.** 먼저 담긴 것이 먼저 받아져야
        다음 실행이 이번과 같은 순서로 선다.

        같은 주소가 두 번 들어 있으면 앞의 것만 남긴다. 뒤의 것을 살려 두어도
        카드는 주소당 하나뿐이라 짝이 맞지 않고, 대기열에 같은 주소가 둘이면
        그 항목만 두 번 받으러 간다.
        """
        if not isinstance(raw, list):
            return []
        out: List[Dict[str, str]] = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = _text(item.get("url")).strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"url": url,
                        "title": _text(item.get("title")),
                        "thumbnail": _text(item.get("thumbnail"))})
        return out

    def entries(self) -> List[Dict[str, str]]:
        """담긴 것을 대기열 차례대로 내준다."""
        return list(self._items)

    def replace(self, items: Iterable[Dict[str, str]]) -> None:
        """담긴 것을 통째로 갈아 끼운다. 파일에 쓰는 일은 save()가 한다.

        덧붙이지 않고 갈아 끼우는 것은 대기열이 '지금 남은 것 전부'로만 뜻이
        서기 때문이다. 빠진 것을 따로 지워 달라고 하면 지우는 자리를 하나라도
        빠뜨렸을 때 이미 받은 항목이 다음 실행에 되살아난다.
        """
        self._items = self._clean(list(items))

    def save(self) -> bool:
        """지금 담긴 것을 파일에 쓴다. 성공 여부를 돌려준다.

        임시 파일에 썼다가 바꿔치기한다. 이 파일은 앱을 끝내는 길목에서 쓰이므로
        쓰는 도중에 프로세스가 사라지는 일이 실제로 일어날 수 있는데, 그때 반쯤
        쓰인 파일이 남으면 다음 실행에서 대기열을 통째로 못 읽는다.
        """
        target = Path(self.path)
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(target)
            return True
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False
