"""테스트 스크립트가 어디서 실행되든 프로젝트 루트를 기준으로 돌게 맞춘다.

src 패키지를 import 하려면 루트가 sys.path에 있어야 하고, 설정 파일 경로가
상대 경로라서 작업 디렉터리도 루트여야 한다. 두 가지를 스크립트마다 따로
챙기면 실행 위치에 따라 결과가 달라지므로 여기서 한 번에 처리한다.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
"""앱이 내려받아 두는 yt-dlp/ffmpeg 위치. 실제 파일이 필요한 테스트가 여기를 쓴다."""

OUT_DIR = Path(os.environ.get("TVD_TEST_OUT", Path(tempfile.gettempdir()) / "tvd-test-out"))
"""렌더 결과 PNG를 모으는 곳. 저장소를 더럽히지 않도록 기본값은 임시 폴더다."""


def setup() -> Path:
    """import 경로와 작업 디렉터리를 루트로 맞추고 출력 폴더를 만든다.

    표준 출력도 함께 손본다. 윈도우 콘솔 기본 인코딩(cp949)으로는 일본어 장음
    기호나 줄표를 찍는 순간 UnicodeEncodeError로 테스트가 통째로 죽는다.
    검증 대상이 일본 방송 제목이라 이런 글자가 결과에 섞이는 게 정상이므로,
    출력 쪽을 UTF-8로 바꾸고 그래도 안 되는 글자는 대체 문자로 흘려보낸다.
    """
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(ROOT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    return ROOT
