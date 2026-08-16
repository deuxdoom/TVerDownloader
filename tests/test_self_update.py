"""자동 업데이트의 계산 부분.

**여기가 틀리면 앱이 사라진다.** 교체는 배치가 하지만, 무엇을 교체할지 정하고
받은 파일이 온전한지 가리는 판단은 전부 파이썬 쪽이다. 깨진 zip으로 교체를
시작하면 되돌릴 원본까지 이미 옮긴 뒤라 손쓸 수가 없다.

배치 내용도 문자열이라 여기서 본다. 실제로 돌려 보는 것은 tools/ 몫이지만,
**절대 들어가면 안 되는 것**(taskkill·powershell·자기 삭제)이 섞여 들어가는 것은
문자열 검사로 잡을 수 있다. 오탐을 줄이려고 일부러 뺀 것들이라, 나중에 누가
편하다고 되살리면 백신에 걸리기 시작한다.
"""

import zipfile
from pathlib import Path

import pytest

from src import self_update
from src.updater import _norm, _newer


def make_zip(path: Path, names) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"" if name.endswith("/") else b"x")
    return path


class TestSupported:
    def test_소스로_돌릴_때는_꺼진다(self):
        """개발 중인 작업 폴더를 릴리스 내용으로 덮어쓰면 고치던 것이 날아간다.

        autostart가 같은 이유로 같은 판단을 한다.
        """
        assert self_update.supported() is False

    def test_꺼져_있으면_폴더도_알려_주지_않는다(self):
        assert self_update.app_dir() is None
        assert self_update.work_dir() is None


class TestPickAsset:
    def test_zip을_고른다(self):
        assets = [{"name": "notes.txt", "browser_download_url": "u1"},
                  {"name": "TVerDownloader_v330.zip", "browser_download_url": "u2"}]
        assert self_update.pick_asset(assets)["browser_download_url"] == "u2"

    def test_주소가_없으면_고르지_않는다(self):
        assert self_update.pick_asset([{"name": "a.zip"}]) is None

    @pytest.mark.parametrize("assets", [[], None, [{"name": "a.exe", "browser_download_url": "u"}]])
    def test_zip이_없으면_None(self, assets):
        assert self_update.pick_asset(assets) is None


class TestFindPayloadRoot:
    def test_폴더로_감싼_경우(self):
        """지금 릴리스가 이 모양이다."""
        names = ["TVerDownloader/", "TVerDownloader/TVerDownloader.exe",
                 "TVerDownloader/_internal/", "TVerDownloader/_internal/base.pyd"]
        assert self_update.find_payload_root(names) == "TVerDownloader/"

    def test_감싸지_않은_경우(self):
        """압축 방식이 바뀌어도 조용히 실패하지 않도록 두 모양을 다 받는다."""
        names = ["TVerDownloader.exe", "_internal/", "_internal/base.pyd"]
        assert self_update.find_payload_root(names) == ""

    def test_폴더_이름이_달라도_찾는다(self):
        names = ["dist-3.4.0/TVerDownloader.exe", "dist-3.4.0/_internal/base.pyd"]
        assert self_update.find_payload_root(names) == "dist-3.4.0/"

    def test_exe만_있으면_못_찾은_것으로_본다(self):
        assert self_update.find_payload_root(["TVerDownloader.exe"]) is None

    def test_internal만_있으면_못_찾은_것으로_본다(self):
        assert self_update.find_payload_root(["_internal/base.pyd"]) is None

    def test_엉뚱한_zip이면_None(self):
        assert self_update.find_payload_root(["readme.txt", "src/main.py"]) is None

    def test_역슬래시로_적힌_항목도_읽는다(self):
        names = ["TVerDownloader\\TVerDownloader.exe", "TVerDownloader\\_internal\\base.pyd"]
        assert self_update.find_payload_root(names) == "TVerDownloader/"


class TestVerifyPackage:
    def test_멀쩡한_꾸러미는_통과한다(self, tmp_path):
        zip_path = make_zip(tmp_path / "ok.zip",
                            ["TVerDownloader/TVerDownloader.exe",
                             "TVerDownloader/_internal/base.pyd"])
        ok, root, message = self_update.verify_package(zip_path)
        assert ok is True and root == "TVerDownloader/" and message == ""

    def test_없는_파일은_막는다(self, tmp_path):
        ok, _, message = self_update.verify_package(tmp_path / "없음.zip")
        assert ok is False and message

    def test_빈_파일은_막는다(self, tmp_path):
        empty = tmp_path / "empty.zip"
        empty.write_bytes(b"")
        ok, _, message = self_update.verify_package(empty)
        assert ok is False and message

    def test_zip이_아니면_막는다(self, tmp_path):
        junk = tmp_path / "junk.zip"
        junk.write_bytes(b"this is not a zip file at all")
        ok, _, message = self_update.verify_package(junk)
        assert ok is False and "열지 못했습니다" in message

    def test_받다_만_파일은_막는다(self, tmp_path):
        """열리기는 해도 끝이 깨진 경우. 여기서 못 걸러내면 교체가 시작된다."""
        zip_path = make_zip(tmp_path / "cut.zip",
                            ["TVerDownloader/TVerDownloader.exe",
                             "TVerDownloader/_internal/base.pyd"])
        data = zip_path.read_bytes()
        zip_path.write_bytes(data[:len(data) // 2])
        ok, _, message = self_update.verify_package(zip_path)
        assert ok is False and message

    def test_내용이_망가진_파일은_CRC로_잡는다(self, tmp_path):
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("TVerDownloader/TVerDownloader.exe", b"hello world")
            archive.writestr("TVerDownloader/_internal/base.pyd", b"x")
        raw = bytearray(zip_path.read_bytes())
        raw[raw.index(b"hello world")] = ord("H")
        zip_path.write_bytes(bytes(raw))
        ok, _, message = self_update.verify_package(zip_path)
        assert ok is False and "손상" in message

    def test_이름만_맞는_다른_zip은_막는다(self, tmp_path):
        zip_path = make_zip(tmp_path / "other.zip", ["readme.txt", "docs/guide.md"])
        ok, _, message = self_update.verify_package(zip_path)
        assert ok is False and "찾지 못했습니다" in message


class TestExtractPayload:
    def test_감싼_폴더를_벗겨_낸다(self, tmp_path):
        """배치가 옮길 자리를 하나로 고정해야 해서, 어느 모양으로 오든 결과는 같다."""
        zip_path = make_zip(tmp_path / "p.zip",
                            ["TVerDownloader/TVerDownloader.exe",
                             "TVerDownloader/_internal/base.pyd"])
        out = tmp_path / "new"
        self_update.extract_payload(zip_path, "TVerDownloader/", out)
        assert (out / "TVerDownloader.exe").is_file()
        assert (out / "_internal" / "base.pyd").is_file()

    def test_감싸지_않은_것도_같은_모양이_된다(self, tmp_path):
        zip_path = make_zip(tmp_path / "p.zip",
                            ["TVerDownloader.exe", "_internal/base.pyd"])
        out = tmp_path / "new"
        self_update.extract_payload(zip_path, "", out)
        assert (out / "TVerDownloader.exe").is_file()
        assert (out / "_internal" / "base.pyd").is_file()

    def test_진행_상황을_알린다(self, tmp_path):
        zip_path = make_zip(tmp_path / "p.zip",
                            ["TVerDownloader.exe", "_internal/base.pyd"])
        seen = []
        self_update.extract_payload(zip_path, "", tmp_path / "new",
                                    lambda i, n: seen.append((i, n)))
        assert seen and seen[-1][0] == seen[-1][1]


class TestStagedPayloadOk:
    def test_다_갖춰지면_통과(self, tmp_path):
        new = tmp_path / self_update.NEW_DIR_NAME
        (new / "_internal").mkdir(parents=True)
        (new / "_internal" / "base.pyd").write_bytes(b"x")
        (new / "TVerDownloader.exe").write_bytes(b"MZ")
        assert self_update.staged_payload_ok(tmp_path) is True

    def test_exe가_없으면_막는다(self, tmp_path):
        new = tmp_path / self_update.NEW_DIR_NAME
        (new / "_internal").mkdir(parents=True)
        (new / "_internal" / "base.pyd").write_bytes(b"x")
        assert self_update.staged_payload_ok(tmp_path) is False

    def test_exe가_비어_있으면_막는다(self, tmp_path):
        """백신이 파일을 격리해 가면 크기 0으로 남는 경우가 있다."""
        new = tmp_path / self_update.NEW_DIR_NAME
        (new / "_internal").mkdir(parents=True)
        (new / "_internal" / "base.pyd").write_bytes(b"x")
        (new / "TVerDownloader.exe").write_bytes(b"")
        assert self_update.staged_payload_ok(tmp_path) is False

    def test_internal이_비면_막는다(self, tmp_path):
        new = tmp_path / self_update.NEW_DIR_NAME
        (new / "_internal").mkdir(parents=True)
        (new / "TVerDownloader.exe").write_bytes(b"MZ")
        assert self_update.staged_payload_ok(tmp_path) is False


class TestBuildBatch:
    @pytest.fixture
    def batch(self):
        return self_update.build_batch(Path(r"C:\app"), Path(r"C:\app\update-workspace"), 4242)

    def test_그_PID가_사라지기를_기다린다(self, batch):
        assert "4242" in batch
        assert "tasklist" in batch

    def test_find이_아니라_findstr을_쓴다(self, batch):
        """chcp 65001에서 find는 파이프로 들어온 글을 읽지 못한다(실측).

        프로세스가 살아 있는데도 '없다'고 답하고, 그 답을 믿으면 아직 도는
        프로그램 위에 파일을 덮어쓴다. 실패 방향이 가장 나쁜 쪽이라 못 박아 둔다.
        """
        assert "findstr" in batch
        assert "| find " not in batch

    def test_되돌리기_경로가_있다(self, batch):
        assert ":restore" in batch
        assert batch.count("goto restore") >= 4

    def test_기다리다_지치면_아무것도_건드리지_않는다(self, batch):
        assert ":give_up" in batch
        assert "하나도 건드리지 않았습니다" in batch

    def test_끝나면_다시_띄운다(self, batch):
        assert 'start "" "%APP_DIR%\\%EXE_NAME%"' in batch

    def test_사용자_파일은_건드리지_않는다(self, batch):
        """bin·설정·기록은 사용자 것이다. 버전이 올라가도 그대로 써야 한다."""
        for keep in ("bin", "downloader_config.json", "favorites.json",
                     "urlhistory.json", "thumbnails"):
            assert keep not in batch

    @pytest.mark.parametrize("banned,why", [
        ("taskkill", "남의 프로세스를 강제로 끝내는 것은 신호가 세다"),
        ("powershell", "cmd 내장 명령만 쓴다"),
        ("certutil", "스크립트 안의 내려받기는 드로퍼로 읽힌다"),
        ("bitsadmin", "같은 이유"),
        ("curl", "같은 이유"),
        ("%~f0", "자기 자신을 지우는 것은 흔적 지우기로 읽힌다"),
        ("attrib", "숨김 속성을 걸지 않는다"),
    ])
    def test_백신이_싫어하는_것은_넣지_않는다(self, batch, banned, why):
        """편하다고 되살리면 오탐이 나기 시작한다. 이유는 self_update 모듈 설명에 있다."""
        assert banned not in batch.lower(), why

    def _region(self, batch, label, goto):
        """label 줄부터 그 label로 되돌아가는 goto 줄까지."""
        lines = batch.splitlines()
        start = next(i for i, l in enumerate(lines) if l.strip() == label)
        stop = next(i for i, l in enumerate(lines) if i > start and l.strip() == goto)
        return lines[start:stop + 1]

    @pytest.mark.parametrize("label,goto", [
        (":waitloop", "goto waitloop"),
        (":move_retry_loop", "goto move_retry_loop"),
    ])
    def test_되돌아가는_구간에는_한국어를_쓰지_않는다(self, batch, label, goto):
        """cmd는 배치를 바이트 오프셋으로 되짚는다.

        chcp 65001에서 UTF-8 한글이 섞여 있으면 goto로 되돌아간 뒤 줄 **중간부터**
        실행되어, 주석의 꼬리가 명령이 된다. 실제로 이렇게 나왔다.

            '믿으면' is not recognized as an internal or external command,
            '파일을' is not recognized as an internal or external command,

        앞으로만 가는 구간의 한국어는 멀쩡하다(실측). 되돌아가는 두 구간만 막는다.
        """
        offenders = [l for l in self._region(batch, label, goto)
                     if any(ord(c) > 127 for c in l)]
        assert offenders == [], f"{label} 안에 비ASCII가 있다: {offenders}"

    def test_옮기기는_모두_재시도를_거친다(self, batch):
        """백신이 갓 풀린 파일을 붙잡고 있으면 'Access is denied'가 난다.

        카스퍼스키에서 실제로 이 자리에서 실패했다. 한 번에 포기하면 멀쩡한
        업데이트가 되돌리기로 끝난다.
        """
        assert batch.count("call :move_retry") == 6
        bare = [l.strip() for l in batch.splitlines() if l.strip().startswith("move ")]
        assert bare == ["move %1 %2 >nul 2>&1"], (
            f"재시도를 거치지 않는 move가 남아 있다: {bare}")

    def test_닫힌_뒤_잠시_뜸을_들인다(self, batch):
        """닫히자마자 건드리면 백신이 그 프로세스의 파일을 아직 훑고 있다."""
        closed = batch[batch.index(":closed"):batch.index("기존 파일을 백업")]
        assert "timeout" in closed

    def test_무엇을_하는지_적어_둔다(self, batch):
        """사람이 열어 봤을 때 읽히면 백신 심사에도 유리하다."""
        assert "rem" in batch
        assert "TVer Downloader" in batch

    def test_경로를_그대로_넣는다(self, batch):
        assert r"C:\app" in batch
        assert r"C:\app\update-workspace" in batch

    def test_exe_이름을_바꿔_넣을_수_있다(self):
        """검사에서 진짜 exe 대신 안전한 것을 넣어 끝까지 돌려 보기 위해서다."""
        batch = self_update.build_batch(Path(r"C:\a"), Path(r"C:\a\w"), 1, exe_name="probe.cmd")
        assert "probe.cmd" in batch


class TestVersionCompare:
    @pytest.mark.parametrize("tag,expected", [
        ("v3.3.0", (3, 3, 0)), ("3.3.0", (3, 3, 0)), ("v3.3", (3, 3, 0)),
        ("v3.3.0-beta", (3, 3, 0)), ("v3.3.0+build5", (3, 3, 0)), ("", (0, 0, 0)),
    ])
    def test_태그를_숫자로_읽는다(self, tag, expected):
        assert _norm(tag) == expected

    @pytest.mark.parametrize("cur,latest", [
        ("3.2.0", "v3.3.0"), ("3.3.0", "v3.3.1"), ("3.3.0", "v4.0.0"),
    ])
    def test_새_버전을_알아본다(self, cur, latest):
        assert _newer(cur, latest) is True

    @pytest.mark.parametrize("cur,latest", [
        ("3.3.0", "v3.3.0"), ("3.3.0", "v3.2.0"), ("3.3.0", ""),
    ])
    def test_같거나_낮으면_알리지_않는다(self, cur, latest):
        assert _newer(cur, latest) is False
