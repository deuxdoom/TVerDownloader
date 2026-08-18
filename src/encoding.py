"""재인코딩할 때 ffmpeg에 넘길 인자를 정하는 곳.

**여기에 Qt를 들이지 않는다.** 고르는 일은 값 계산뿐이라 창이 없어도 검사할 수
있고, 인코딩 인자가 틀렸을 때 화면이 아니라 이 표를 보면 되도록 한자리에 모았다.
실제로 ffprobe를 부르고 ffmpeg를 띄우는 일은 ConversionThread가 맡는다.

값은 Scene의 x264 TV 릴리스 표준(CRF 19~24, preset slow 이상, 해상도·fps 기준
level)에서 가져오되 **한두 단계 낮게** 잡았다. 그 표준은 블루레이·방송 원본처럼
손실이 없는 소스를 전제하는데, 우리가 다루는 것은 이미 손실 압축된 스트림이라
다시 압축하면 세대 손실이 겹친다. NVENC 쪽이 CPU보다 낮은 것은 하드웨어
인코더가 같은 품질 지수에서 압축 효율이 더 떨어지기 때문이다.

**tune은 걸지 않는다.** x264의 tune film은 deblock을 -1,-1로 낮춰 미세한 결을
살리는 설정인데, 그것이 지켜 주는 결이 우리 소스에서는 원본의 결이 아니라
**앞선 인코딩이 남긴 블로킹 아티팩트**다. 깎여야 할 것을 지키느라 비트를 쓰는
셈이라 손해가 겹친다. tune 없는 기본값(deblock 0,0)이 이미 압축된 소스에 맞다.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

AUDIO_LADDER_KBPS = (96, 128, 160, 192)
"""오디오를 다시 만들 때 고를 수 있는 비트레이트(스테레오 기준, kbps).

고정값 하나를 쓰면 96k짜리 원본을 192k로 부풀리게 되어 용량만 늘고 음질은
그대로다. 원본 이상인 가장 낮은 단계를 골라 **부풀리지도 굶기지도 않는다.**
맨 끝이 상한이다 - 그 위는 AAC-LC가 스테레오에서 이미 투명에 가까워, 더 줘도
돌아오는 것이 없다.
"""

AUDIO_LADDER_TOLERANCE = 0.03
"""사다리 단계를 고를 때 눈감아 주는 초과분(비율).

실측한 비트레이트는 표기값보다 늘 조금 높다(96k 원본이 96,064bps, 120k가
120,080bps로 나온다). 이걸 그대로 견주면 96k 원본이 첫 단계를 넘겨 128k로
올라가 **용량이 33% 늘어난다.** 반대로 넉넉히 잡아 131k짜리가 128k로 내려가는
쪽은 2%대 손해라 귀에 닿지 않는다. 실패 방향이 한쪽으로만 아프므로 넉넉히 둔다.
"""

AUDIO_FALLBACK_KBPS = 128
"""비트레이트를 끝내 재지 못했을 때 쓸 값(스테레오 기준).

사다리 한가운데다. 스트리밍 오디오가 대개 이 근처(유튜브 Opus 128k, TVer AAC
128~192k)라 어느 쪽으로 틀려도 한 단계 안에서 빗나간다. **여기까지 오는 일은
드물다** - 컨테이너가 안 알려 주면 패킷을 세어 직접 재고, 그것까지 실패해야
이 값이 쓰인다.
"""

AUDIO_COPY_CODECS = frozenset({"aac"})
"""다시 만들지 않고 그대로 옮길 오디오 코덱.

이미 AAC면 건드릴 이유가 없다. 세대 손실도 없고 용량도 그대로라 어느 쪽으로도
손해가 없는 유일한 경우다.
"""

AUDIO_PROBE_WINDOW_SECONDS = 120
"""비트레이트를 직접 잴 때 훑을 앞부분 길이(초).

컨테이너가 스트림 비트레이트를 안 적어 두면(mkv·webm이 그렇다) 패킷 크기를
더해서 재는 수밖에 없는데, 파일 전체를 훑으면 한 시간짜리에서 그만큼 기다린다.
앞 2분이면 값이 충분히 안정된다(실측: 20분짜리 160k 파일에서 159,998bps,
0.068초. 전체를 훑으면 0.205초에 패킷 60,001개).
"""

KEYINT = 250
"""키프레임 간격(프레임 수).

fps로 나누면 24fps에서 10.4초, 30fps에서 8.3초, 60fps에서 4.2초다. 세 구간 모두
흔히 쓰는 범위 안에 들어와서 fps마다 값을 달리 잡을 이유가 없다. 오히려 프레임
수로 고정해 두면 **fps가 높을수록 간격이 촘촘해져**, 60fps 소스에서 되감기가
빨라지는 쪽으로 저절로 기운다.
"""

DEFAULT_COLOR = "bt709"
"""소스에 색 정보가 없을 때 새겨 넣을 값. HD 방송·스트리밍의 사실상 표준이다."""

COLOR_UNSPECIFIED = frozenset({"", "unknown", "unspecified", "reserved", "n/a"})
"""ffprobe가 모른다는 뜻으로 내놓는 표기들."""

ENCODER_PROFILES: Dict[Tuple[str, str], Tuple[str, Tuple[str, ...]]] = {
    ("h264", "cpu"): ("libx264", ("-crf", "20", "-preset", "slow")),
    ("h264", "nvidia"): ("h264_nvenc", ("-rc", "vbr", "-cq", "19", "-preset", "p6", "-b:v", "0")),
    ("hevc", "cpu"): ("libx265", ("-crf", "23", "-preset", "slow")),
    ("hevc", "nvidia"): ("hevc_nvenc", ("-rc", "vbr", "-cq", "22", "-preset", "p6", "-b:v", "0")),
}
"""코덱과 가속 방식에 따라 정해지는 인코더와 품질 인자.

**설정으로 열지 않는다.** 예전에는 CRF/CQ를 사용자가 숫자로 넣게 두었는데,
고를 근거가 화면에 없어 눈대중이 될 수밖에 없었다. 여기 적힌 값은 근거가 있고
(모듈 docstring), 근거가 바뀌면 이 표만 고치면 된다.

**NVENC에 -b:v 0을 함께 준다.** 이 빌드에서는 -rc vbr -cq 만으로도 결과가
같지만(실측: -b:v 유무로 22,995,286바이트 동일), 드라이버에 따라 기본
비트레이트가 CQ를 덮어쓰는 경우가 있어 못 박아 둔다.
"""

LEVEL_TABLE: Dict[str, Tuple[Tuple[bool, bool, str], ...]] = {
    "h264": (
        (True, True, "5.2"),
        (True, False, "5.1"),
        (False, True, "4.2"),
        (False, False, "4.1"),
    ),
    "hevc": (
        (True, True, "5.2"),
        (True, False, "5.1"),
        (False, True, "4.1"),
        (False, False, "4.1"),
    ),
}
"""(2160p급인가, 30fps를 넘는가) -> level. 코덱마다 표가 다르다.

**HEVC에는 4.2가 없다.** AVC와 같은 표를 쓰면 1080p 60fps 소스를 HEVC로 옮길 때
x265가 'specified level 42 does not exist'를 내고 인코딩이 통째로 실패한다
(실측). HEVC의 4.1은 1080p 60fps를 이미 담으므로(최대 휘도 표본율 133,693,440 >=
1920x1080x60 = 124,416,000) 그 칸을 4.1로 둔다.
"""

FALLBACK_LEVEL = "5.2"
"""해상도나 fps를 읽지 못했을 때 쓸 level.

가장 높은 것으로 간다. 낮게 잡으면 그 level에 담기지 않는 영상에서 인코딩이
실패하거나 규격을 어긴 파일이 나오는데, 높게 잡아서 생기는 손해는 아주 오래된
재생기가 파일을 거절할 수 있다는 것뿐이다. 실패 방향이 덜 아픈 쪽으로 둔다.
"""

UHD_MIN_HEIGHT = 1081
FAST_MIN_FPS = 30.0

HVC1_TAG_CONTAINERS = frozenset({".mp4", ".mov", ".m4v"})
"""HEVC를 이 컨테이너에 담을 때는 hvc1 태그를 붙인다.

ffmpeg 기본값은 hev1인데, 퀵타임 계열과 편집 도구(프리미어 프로 포함)가 그쪽을
잘 못 읽는다. 담기는 내용은 같고 태그 네 글자만 다르다.
"""


def _is_unspecified(value: Optional[str]) -> bool:
    """ffprobe가 내놓은 값이 모른다는 뜻인지."""
    return (value or "").strip().lower() in COLOR_UNSPECIFIED


def audio_bitrate_kbps(source_kbps: Optional[float], channels: Optional[int]) -> int:
    """원본 오디오에 맞는 재인코딩 비트레이트(kbps)를 고른다.

    사다리는 스테레오 기준이라 채널 수에 맞춰 늘린다. **5.1을 스테레오 사다리로
    그냥 재면 채널당 비트레이트가 굶는다** - 384k짜리 5.1(채널당 64k)이 상한
    192k에 눌려 채널당 32k가 되어 버린다. 스테레오 몇 쌍인지로 환산해서 고르고,
    고른 뒤 같은 비율로 되돌리면 채널이 몇 개든 채널당 배분이 유지된다.
    """
    pairs = max(1, channels or 2) / 2.0
    if source_kbps is None or source_kbps <= 0:
        return int(round(AUDIO_FALLBACK_KBPS * pairs))
    per_pair = source_kbps / pairs
    for rung in AUDIO_LADDER_KBPS:
        if per_pair <= rung * (1.0 + AUDIO_LADDER_TOLERANCE):
            return int(round(rung * pairs))
    return int(round(AUDIO_LADDER_KBPS[-1] * pairs))


def audio_args(codec_name: Optional[str], source_kbps: Optional[float],
               channels: Optional[int]) -> Tuple[List[str], str]:
    """오디오 인자와 그 이유 한 줄을 함께 돌려준다.

    **영상을 다시 만들 때 오디오를 복사하면 안 된다.** 예전에는 -c:a copy 가
    박혀 있어서, AV1+Opus 원본을 AVC로 옮기면 영상만 h264가 되고 소리는 Opus로
    남았다. Opus는 프리미어 프로 같은 편집 도구에서 오디오 트랙 자체가 잡히지
    않아, 겉보기에는 멀쩡한 mp4가 쓸 수 없는 파일이 된다.

    소리가 아예 없는 파일에는 아무것도 붙이지 않는다. 붙여 봐야 ffmpeg가 옮길
    스트림이 없어 무시하는데, 명령줄에만 남아 로그를 읽을 때 헷갈린다.
    """
    if not codec_name:
        return [], "오디오 없음 (인자 없음)"
    if codec_name.lower() in AUDIO_COPY_CODECS:
        return ["-c:a", "copy"], f"{codec_name} 그대로 복사 (재인코딩 없음)"
    target = audio_bitrate_kbps(source_kbps, channels)
    measured = f"{source_kbps:.0f}kbps" if source_kbps else "비트레이트 미상"
    return (["-c:a", "aac", "-b:a", f"{target}k"],
            f"{codec_name} {measured} {channels or 2}ch -> aac {target}kbps")


def bitrate_from_packets(rows: Sequence[Sequence[str]]) -> Optional[float]:
    """(pts_time, size) 줄들을 더해 비트레이트(kbps)를 낸다. 못 재면 None.

    컨테이너가 스트림 비트레이트를 안 적어 두는 경우(mkv·webm)를 위한 것이다.
    **그쪽이 예외가 아니라 주 경로다** - yt-dlp가 유튜브의 AV1+Opus를 병합하면
    mkv로 나오고, 이 버그를 만든 파일이 바로 그것이었다.

    걸린 시간은 첫 패킷과 끝 패킷의 간격에 패킷 한 개분을 더해서 잡는다. 끝
    패킷도 제 길이만큼 소리를 담고 있어서, 빼고 재면 그 몫이 통째로 빠진다.
    """
    times: List[float] = []
    sizes: List[int] = []
    for row in rows:
        if len(row) < 2:
            continue
        try:
            times.append(float(row[0]))
            sizes.append(int(row[1]))
        except (TypeError, ValueError):
            continue
    if len(sizes) < 2:
        return None
    span = times[-1] - times[0]
    if span <= 0:
        return None
    span += span / (len(times) - 1)
    return sum(sizes) * 8.0 / span / 1000.0


def parse_fps(text: Optional[str]) -> Optional[float]:
    """ffprobe의 60000/1001 같은 분수 표기를 실수로 바꾼다."""
    raw = (text or "").strip()
    if not raw or raw in ("0/0", "N/A"):
        return None
    try:
        if "/" in raw:
            num, _, den = raw.partition("/")
            denominator = float(den)
            return float(num) / denominator if denominator else None
        return float(raw)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def video_level(codec: str, width: Optional[int], height: Optional[int],
                fps: Optional[float]) -> str:
    """해상도와 fps로 level을 정한다. 하나라도 못 읽으면 가장 높은 것으로.

    세로로 긴 영상이 들어와도 짧은 쪽을 높이로 보게 두 변 중 작은 쪽으로 잰다.
    그렇게 하지 않으면 세로로 세운 2160 영상이 1080p급으로 잡혀, 담기지 않는
    level이 붙는다.
    """
    if not width or not height or not fps:
        return FALLBACK_LEVEL
    uhd = min(width, height) >= UHD_MIN_HEIGHT
    fast = fps > FAST_MIN_FPS
    for is_uhd, is_fast, level in LEVEL_TABLE.get(codec, LEVEL_TABLE["h264"]):
        if is_uhd == uhd and is_fast == fast:
            return level
    return FALLBACK_LEVEL


def level_args(encoder: str, level: str) -> List[str]:
    """level을 인코더가 알아듣는 형태로 바꾼다.

    **libx265에는 -level 옵션이 아예 없다.** 다른 셋은 -level 4.1 을 그대로
    받지만 이쪽만 -x265-params level-idc=41 로 넣어야 한다.
    """
    if encoder == "libx265":
        return ["-x265-params", "level-idc=" + level.replace(".", "")]
    return ["-level", level]


def color_filter(primaries: Optional[str], transfer: Optional[str],
                 space: Optional[str]) -> str:
    """색 속성을 프레임에 새기는 setparams 필터 문자열.

    **-color_primaries / -color_trc 출력 옵션으로는 안 된다.** 그렇게 주면
    colormatrix만 반영되고 나머지 둘은 조용히 떨어진다(실측: 생 h264
    비트스트림으로 뽑아도 마찬가지라 먹서 문제가 아니다). libx264와 NVENC가
    그 둘을 인코더 설정이 아니라 **프레임에 딸린 값**에서 읽기 때문이고,
    프레임에는 디코더가 넘긴 원본 값(모름)이 실려 있다. setparams는 그 자리에
    직접 적어 넣어서 세 가지가 모두 남는다.

    소스에 있으면 그대로 따라가고, 없을 때만 bt709를 새긴다.
    """
    values = []
    for name, value in (("color_primaries", primaries), ("color_trc", transfer),
                        ("colorspace", space)):
        resolved = DEFAULT_COLOR if _is_unspecified(value) else value.strip()
        values.append(f"{name}={resolved}")
    return "setparams=" + ":".join(values)


def video_args(codec: str, hw_encoder: str, source: Dict[str, Any],
               container_suffix: str = ".mp4") -> Tuple[List[str], str]:
    """영상 인자 전체와 사람이 읽을 요약 한 줄.

    source에는 ffprobe로 읽은 width/height/fps가 들어온다. 못 읽은 항목은
    None이면 되고, 그때는 각 규칙이 저마다 안전한 쪽으로 물러선다.
    """
    key = (codec, "nvidia" if hw_encoder == "nvidia" else "cpu")
    encoder, quality = ENCODER_PROFILES[key]
    level = video_level(codec, source.get("width"), source.get("height"),
                        source.get("fps"))
    args = ["-c:v", encoder]
    args.extend(quality)
    args.extend(level_args(encoder, level))
    args.extend(["-g", str(KEYINT)])
    if codec == "hevc" and container_suffix.lower() in HVC1_TAG_CONTAINERS:
        args.extend(["-tag:v", "hvc1"])
    summary = f"{encoder} ({' '.join(quality)}, level {level}, keyint {KEYINT})"
    return args, summary
