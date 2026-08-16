"""파일명 템플릿 조립.

설정 화면에서 켠 구성 요소와 그 차례가 그대로 yt-dlp의 -o 템플릿이 된다.
여기가 틀리면 파일이 엉뚱한 이름으로 저장되는데, 다 받은 뒤에야 알게 된다.

두 가지가 얽혀 있다. **켤지 말지(filename_parts)와 어느 차례인지(filename_order)**.
차례 목록에 있어도 꺼져 있으면 빠지고, 켜져 있어도 차례 목록에 없으면 빠진다.
그리고 series만은 성격이 달라서, 이름 조각이 아니라 **폴더**를 하나 만든다.
"""

import pytest

from src.utils import construct_filename_template

ALL_ON = {"series": True, "upload_date": True, "episode_number": True,
          "episode": True, "id": True}
FULL_ORDER = ["series", "upload_date", "episode_number", "episode", "id"]


def config(parts, order):
    return {"filename_parts": parts, "filename_order": order}


def test_모두_켜면_모든_조각이_차례대로_들어간다():
    got = construct_filename_template(config(ALL_ON, FULL_ORDER))
    assert got == ("%(series,playlist_title)s/"
                   "%(series)s %(upload_date>%Y-%m-%d)s %(episode_number)s "
                   "%(title)s [%(id)s].%(ext)s")


def test_series를_켜면_시리즈_폴더가_생긴다():
    """series는 이름 조각이면서 동시에 폴더를 만든다. 앞의 '/'가 그 표시다."""
    got = construct_filename_template(config(ALL_ON, FULL_ORDER))
    assert got.startswith("%(series,playlist_title)s/")


def test_series를_끄면_폴더가_사라진다():
    parts = dict(ALL_ON, series=False)
    got = construct_filename_template(config(parts, FULL_ORDER))
    assert "/" not in got
    assert got == "%(upload_date>%Y-%m-%d)s %(episode_number)s %(title)s [%(id)s].%(ext)s"


def test_차례를_바꾸면_그대로_따라간다():
    got = construct_filename_template(config(ALL_ON, ["id", "episode", "series"]))
    assert got == "%(series,playlist_title)s/[%(id)s] %(title)s %(series)s.%(ext)s"


def test_꺼진_조각은_차례에_있어도_빠진다():
    parts = dict(ALL_ON, upload_date=False, id=False)
    got = construct_filename_template(config(parts, FULL_ORDER))
    assert "%(upload_date>%Y-%m-%d)s" not in got
    assert "[%(id)s]" not in got
    assert got == "%(series,playlist_title)s/%(series)s %(episode_number)s %(title)s.%(ext)s"


def test_차례에_없는_조각은_켜져_있어도_빠진다():
    """order가 최종 결정권을 갖는다. parts만 켜도 자리가 없으면 못 들어간다."""
    got = construct_filename_template(config(ALL_ON, ["episode"]))
    assert got == "%(series,playlist_title)s/%(title)s.%(ext)s"


def test_모르는_이름이_차례에_섞여도_무시한다():
    """설정 파일을 손으로 고쳤을 때 앱이 죽지 않아야 한다."""
    got = construct_filename_template(config(ALL_ON, ["episode", "그런거없음", "id"]))
    assert got == "%(series,playlist_title)s/%(title)s [%(id)s].%(ext)s"


def test_episode는_title로_바뀐다():
    """설정 화면의 '에피소드'는 yt-dlp에서 title이다. 이름이 달라 헷갈리는 자리."""
    parts = {"episode": True}
    got = construct_filename_template(config(parts, ["episode"]))
    assert got == "%(title)s.%(ext)s"


def test_설정이_비어_있어도_죽지_않는다():
    """확장자만 남는다. 이름이 비는 것은 아래 검사가 따로 기록해 둔다."""
    assert construct_filename_template({}) == ".%(ext)s"


def test_모든_조각을_꺼도_확장자는_남는다():
    parts = {k: False for k in ALL_ON}
    assert construct_filename_template(config(parts, FULL_ORDER)) == ".%(ext)s"


@pytest.mark.xfail(reason="series만 켜고 차례를 비우면 이름이 빈 파일이 된다. "
                          "지금 동작을 기록해 둔 것이고 고친 적은 없다.",
                   strict=True)
def test_series만_켜고_차례가_비면_이름이_빈다():
    """알려진 구멍.

    `%(series,playlist_title)s/.%(ext)s`가 되어 폴더 안에 '.mp4'처럼 이름 없는
    파일이 생긴다. 설정 화면에서는 만들 수 없는 조합이고(차례 목록이 늘 차 있다)
    설정 파일을 손으로 비웠을 때만 나온다. 고치려면 조각이 하나도 없을 때
    title로 되돌리는 처리가 필요한데, 그건 동작 변경이라 따로 판단할 일이다.
    """
    got = construct_filename_template(config({"series": True}, []))
    assert got != "%(series,playlist_title)s/.%(ext)s"
