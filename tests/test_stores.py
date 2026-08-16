"""기록·즐겨찾기 저장소.

파일을 건드리지만 tmp_path 안에서만 논다. 진짜 urlhistory.json이나
favorites.json은 손대지 않는다.

여기서 보는 것은 **다시 읽었을 때 같은 것이 나오는가**다. 저장이 깨지면 받은
목록이 통째로 사라지는데, 앱을 다시 켜기 전까지는 알 수 없다.
"""

import json

import pytest

from src.history_store import HistoryStore
from src.favorites_store import FavoritesStore

URL = "https://tver.jp/episodes/ep1"
SERIES = "https://tver.jp/series/sr1"


@pytest.fixture
def history(tmp_path):
    store = HistoryStore(path=str(tmp_path / "urlhistory.json"),
                         backup_dir=tmp_path / "bak")
    store.load()
    return store


@pytest.fixture
def favorites(tmp_path):
    store = FavoritesStore(str(tmp_path / "favorites.json"))
    store.load()
    return store


class TestHistoryStore:
    def test_없는_파일을_읽어도_빈_채로_시작한다(self, history):
        assert history.sorted_entries() == []

    def test_담고_찾는다(self, history):
        history.add(URL, "제1화", "C:/dl/ep1.mp4")
        assert history.exists(URL) is True
        assert history.get_title(URL) == "제1화"

    def test_담지_않은_것은_없다고_한다(self, history):
        assert history.exists("https://tver.jp/episodes/없음") is False

    def test_지운다(self, history):
        history.add(URL, "제1화")
        history.remove(URL)
        assert history.exists(URL) is False

    def test_없는_것을_지워도_죽지_않는다(self, history):
        history.remove("https://tver.jp/episodes/없음")

    def test_같은_주소를_다시_담으면_덮어쓴다(self, history):
        history.add(URL, "옛 제목")
        history.add(URL, "새 제목")
        assert history.get_title(URL) == "새 제목"
        assert len(history.sorted_entries()) == 1

    def test_저장하고_다시_읽으면_그대로다(self, tmp_path):
        """비동기 저장이라 _save_sync를 직접 불러 기다린다."""
        path = tmp_path / "urlhistory.json"
        store = HistoryStore(path=str(path), backup_dir=tmp_path / "bak")
        store.load()
        store.add(URL, "제1화", "C:/dl/ep1.mp4", series_id="sr1", thumbnail_url="http://t/1.jpg")
        store._save_sync(dict(store._data))

        again = HistoryStore(path=str(path), backup_dir=tmp_path / "bak")
        assert again.load() is True
        assert again.get_title(URL) == "제1화"

    def test_깨진_파일은_빈_채로_열되_실패를_알린다(self, tmp_path):
        """조용히 성공한 척하면 그 위에 덮어써서 남은 것까지 날린다."""
        path = tmp_path / "urlhistory.json"
        path.write_text("{이건 JSON이 아니다", encoding="utf-8")
        store = HistoryStore(path=str(path), backup_dir=tmp_path / "bak")
        assert store.load() is False
        assert store.sorted_entries() == []

    def test_예전_리스트_형식도_읽는다(self, tmp_path):
        """옛 버전이 남긴 파일. 못 읽으면 기록이 통째로 사라진 것처럼 보인다."""
        path = tmp_path / "urlhistory.json"
        path.write_text(json.dumps([
            {"url": URL, "title": "제1화", "date": "2026-08-16", "filepath": "C:/dl/ep1.mp4"}
        ], ensure_ascii=False), encoding="utf-8")
        store = HistoryStore(path=str(path), backup_dir=tmp_path / "bak")
        assert store.load() is True
        assert store.get_title(URL) == "제1화"


class TestFavoritesStore:
    def test_없는_파일을_읽어도_빈_채로_시작한다(self, favorites):
        assert favorites.list_series() == []

    def test_담고_찾는다(self, favorites):
        favorites.add(SERIES)
        assert favorites.exists(SERIES) is True
        assert SERIES in favorites.list_series()

    def test_같은_시리즈를_두_번_담아도_하나다(self, favorites):
        favorites.add(SERIES)
        favorites.add(SERIES)
        assert len(favorites.list_series()) == 1

    def test_지운다(self, favorites):
        favorites.add(SERIES)
        favorites.remove(SERIES)
        assert favorites.exists(SERIES) is False

    def test_확인_시각과_제목을_적어_둔다(self, favorites):
        favorites.add(SERIES)
        favorites.touch_last_check(SERIES, "아메토크")
        entries = dict(favorites.sorted_entries())
        assert entries[SERIES].get("title") == "아메토크"

    def test_저장하고_다시_읽으면_그대로다(self, tmp_path):
        path = tmp_path / "favorites.json"
        store = FavoritesStore(str(path))
        store.load()
        store.add(SERIES)
        store.touch_last_check(SERIES, "아메토크")
        store.save()

        again = FavoritesStore(str(path))
        again.load()
        assert again.exists(SERIES) is True
        assert dict(again.sorted_entries())[SERIES].get("title") == "아메토크"

    def test_깨진_파일이어도_죽지_않는다(self, tmp_path):
        path = tmp_path / "favorites.json"
        path.write_text("{망가짐", encoding="utf-8")
        store = FavoritesStore(str(path))
        store.load()
        assert store.list_series() == []
