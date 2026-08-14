![TVerDownloader 메인 UI](main.png)

# <img src="logo.png" width="28" alt="TVer Downloader Logo"> 티버 다운로더 (TVer Downloader)

[![NordVPN 74%할인 + 3개월 무료](https://img.shields.io/badge/NORDVPN-74%25%ED%95%A0%EC%9D%B8%203개월%20무료-0054a6?style=for-the-badge&logo=nordvpn&logoColor=black&labelColor=white)](https://refer-nordvpn.com/RRXwGuSQXTe)
[![후원하기](https://img.shields.io/badge/후원하기-투네이션-ff69b4?style=for-the-badge&logo=githubsponsors)](https://toon.at/donate/deuxdoom)

[![RELEASE](https://img.shields.io/github/release/deuxdoom/TVerDownloader?style=flat&logo=github&logoColor=white&label=RELEASE&labelColor=2f353a&color=0ea5e9)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![Downloads Latest](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/latest/total?logo=github&style=flat&label=DOWNLOADS@LATEST)](https://github.com/deuxdoom/TVerDownloader/releases/latest)
[![Downloads Total](https://img.shields.io/github/downloads/deuxdoom/TVerDownloader/total?logo=github&style=flat&label=DOWNLOADS)](https://github.com/deuxdoom/TVerDownloader/releases)
[![LICENSE](https://img.shields.io/badge/LICENSE-MIT-f43f5e?style=flat&labelColor=2f353a)](https://opensource.org/licenses/MIT)  
[![Platform](https://img.shields.io/badge/PLATFORM-WINDOWS%20X64-blue?style=flat&logo=windows)](https://github.com/deuxdoom/TVerDownloader)
[![PYTHON](https://img.shields.io/badge/PYTHON-3.10%2B-3776ab?style=flat&logo=python&logoColor=white&labelColor=2f353a)](https://www.python.org/)
[![PYQT6](https://img.shields.io/badge/PYQT6-GUI-10b981?style=flat&logo=qt&logoColor=white&labelColor=2f353a)](https://pypi.org/project/PyQt6/)  
[![Made with yt-dlp](https://img.shields.io/badge/made%20with-yt--dlp-orange?style=plastic)](https://github.com/yt-dlp/yt-dlp)
[![Made with FFmpeg](https://img.shields.io/badge/made%20with-FFmpeg-black?style=plastic&logo=ffmpeg)](https://ffmpeg.org/)

---

## 📌 간단 소개

- **TVer Downloader**는 일본 티버 스트리밍 플랫폼의 동영상을 다운로드하도록 도와주는 GUI 기반의 프로그램입니다.
- PyQt6 기반의 직관적인 인터페이스와 yt-dlp/FFmpeg 자동 업데이트 등의 기능을 갖추고 있습니다.
- 기본적으로 TVer의 영상 다운로드가 주목적이지만, YouTube의 영상 역시 다운로드가 가능합니다.

---

## 💻 시스템 요구 사항

- Windows 10 / 11 (x64)
- Python 3.10 이상 (소스로 직접 실행할 경우)
- 인터넷 연결 및 일본 VPN 필요
- 런타임 에러가 발생할 경우: [Microsoft Visual C++ 재배포 가능 패키지 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

## ✨ 주요 기능

### 다운로드
- 최신 **yt-dlp** 및 **FFmpeg** 자동 다운로드 및 업데이트
- **단일 및 다중 다운로드** (시리즈 URL 자동 분해 지원)
- **동시 다운로드 수 조절** (1 ~ 20개)
- **화질 선택** (최상 / 1080p / 720p)
- **시리즈 분석 시 제외 키워드** 설정 (기본값: 予告, SP, ダイジェスト 등)

### 파일 및 변환
- **파일명 구성 요소 커스터마이징** — 항목을 **끌어놓아** 순서를 바꾸고, 실제 방송 예시로 결과를 미리 확인
- 경로가 Windows 길이 제한을 넘을 경우 **폴더 구조를 유지한 채 이름 자동 축소**
- **선호 코덱 설정** — 기본값은 `원본 유지`로 불필요한 재인코딩을 하지 않음 (필요 시 AVC / HEVC / VP9 / AV1 선택 가능)
- **하드웨어 인코딩 가속** 지원 (NVIDIA NVENC / Intel QSV / AMD AMF)
- **컨테이너 변환** (MP4 → AVI / MOV, MP3 오디오 추출)
- 재인코딩을 쓰지 않을 때는 관련 설정이 **흐리게 표시**되어 지금 해당 없음을 알려줌

### 자막
- **일본어 자막 다운로드** 지원
- **영상에 자막 포함**(embed) 또는 **별도 파일로 저장** 선택
- 별도 저장 시 **VTT / SRT 포맷** 선택 가능

### 인터페이스
- **다운로드 카드** — 16:9 썸네일, 상태를 나타내는 세로 색 띠, 진행 중에만 은은하게 밝기가 변하는 애니메이션
- **완료 시 재생 · 폴더 열기 버튼 상시 노출** (더블클릭 재생도 그대로 동작)
- **세그먼트 컨트롤 탭** — 다운로드 / 기록 / 즐겨찾기
- **라이트 / 다크 테마 전환** (헤더 버튼, 기본값 라이트)
- **닫기 버튼(X) 동작 선택** — 트레이로 이동 또는 프로그램 종료
- **썸네일 클릭 확대**, **트레이 알림**, **항상 위**
- **다운로드 기록 및 즐겨찾기 시리즈 목록 자동 백업**
- **썸네일 캐시 관리** 기능
- OS 표시 언어(한국어 · 일본어 · 영어)에 맞춘 **타이틀 로고와 시스템 메뉴**

---

## 🚀 사용 방법

1. TVer 영상 *URL*을 입력 창에 붙여넣기
2. **설정** 메뉴에서 저장 폴더, 화질, 동시 다운로드 수, 파일명 규칙 등 조정
3. **다운로드** 버튼 클릭
4. 진행률·로그·썸네일로 실시간 상태 확인
5. 완료된 항목의 **재생 · 폴더 열기** 버튼으로 바로 접근

### 설정 항목 구성

| 항목 | 내용 |
|---|---|
| 일반 | 저장 폴더, 동시 다운로드 수, 닫기 버튼(X) 동작 |
| 파일명 | 구성 요소 선택 및 끌어놓기 정렬, 실제 예시 미리보기 |
| 화질 | 다운로드 화질, 선호 코덱, 하드웨어 가속, 상세 품질(CRF/CQ) |
| 자막 | 자막 다운로드 여부, 영상 포함/별도 저장, 자막 포맷 |
| 고급 | 컨테이너 변환, 시리즈 제외 키워드, SSL 인증서 검증 |
| 캐시 | 썸네일 캐시 크기 확인 및 삭제 |

---

## ⚠ 주의 사항

- 본 프로그램은 **개인적인 아카이빙 목적**으로만 사용해야 하며, 상업적 이용이나 재배포는 금지됩니다.
- TVer는 일본 내 서비스이므로, **일본 VPN 환경**에서만 정상 동작합니다.
- 다운로드한 콘텐츠의 **저작권 및 이용 약관**을 반드시 준수하세요.
- **Windows에서 'PC 보호' 또는 '서명되지 않은 파일' 경고**가 표시될 수 있습니다.  
이 프로그램은 직접 빌드한 오픈소스 프로젝트로, 소스코드가 있으니 안심하고 실행해도 됩니다.
- **업데이트 시** 반드시 `TVerDownloader.exe` **파일**과 `_internal` **폴더**를 **함께 덮어쓰기** 해야 합니다.
- 네트워크 환경 문제로 다운로드가 실패할 경우, **설정 > 고급**의 `SSL 인증서 검증 건너뛰기`를 활성화하면 해결될 수 있습니다. 단, 보안상 필요한 경우에만 사용하세요.

---

## 🔧 개발 정보

- **GUI**: PyQt6
- **다운로드 엔진**: yt-dlp + FFmpeg (자동 최신화 포함)
- **설정 저장**: JSON 기반(config / history / favorites)
- **서체**: Pretendard(본문) · Pretendard JP(한자) · JetBrains Mono(수치) 번들
- **아이콘**: [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) (MIT) — SVG를 코드에 임베드해 외부 파일 의존 없음
- **안정성**: 예외 발생 시 크래시 로그(`TVerDownloader_crash.log`) 저장

### 소스에서 실행

```bash
pip install PyQt6 requests
python TVerDownloader.py
```

### 빌드

```bash
pip install pyinstaller
pyinstaller TVerDownloader.spec --noconfirm --clean
```

결과물은 `dist/TVerDownloader/`에 생성됩니다. 빌드 설정(서체·로고·번역 번들, 미사용 Qt 모듈 제외)은 모두 `TVerDownloader.spec`에 있습니다.

### 리소스 재생성

`assets/`의 원본을 바꾼 뒤에만 실행하면 됩니다.

```bash
python tools/gen_icons.py        # assets/icons/*.svg  → src/icons_data.py
python tools/gen_titlelogo.py <로고파일...>   # → assets/logo/logo_<lang>_<theme>.png
python tools/font_preview.py     # 글자 렌더링 옵션 비교 (미리보기 전용)
```

---

## 📁 프로젝트 트리구조

```
📦 TVerDownloader
├─ 📄 TVerDownloader.py                     → Entry point / main window bootstrap
├─ 📄 TVerDownloader.spec                   → PyInstaller 빌드 설정 (onedir)
├─ 📂 src
│  ├─ 📄 __init__.py
│  ├─ 📄 utils.py                            → Config, 파일명 템플릿, 리소스 경로, 앱 이름 로컬라이징
│  ├─ 📄 download_manager.py                 → 대기열 및 동시 실행 관리
│  ├─ 📄 series_parser.py                    → 시리즈 URL 분석 코디네이터
│  ├─ 📄 updater.py                          → GitHub releases/latest 확인
│  ├─ 📄 dialogs.py                          → SettingsDialog (좌측 내비게이션 + 스택)
│  ├─ 📄 about_dialog.py                     → 정보 창
│  ├─ 📄 bulk_dialog.py                      → 다중 URL 추가 대화상자
│  ├─ 📄 series_dialog.py                    → 시리즈 회차 선택 (썸네일 미리보기)
│  ├─ 📄 message.py                          → 팔레트를 따르는 예/아니오 확인 창
│  ├─ 📄 widgets.py                          → 다운로드/기록/즐겨찾기 카드 + 색 띠 + 썸네일 캐시
│  ├─ 📄 history_store.py                    → urlhistory.json + 롤링 백업
│  ├─ 📄 favorites_store.py                  → favorites.json + 백업
│  ├─ 📄 qss.py                              → 컬러 토큰(palette)과 라이트/다크 QSS 생성
│  ├─ 📄 icon.py                             → 앱 아이콘 (Base64 → QIcon)
│  ├─ 📄 icons.py                            → Fluent 아이콘을 테마 색으로 렌더
│  ├─ 📄 icons_data.py                       → 임베드된 SVG 19종 (자동 생성)
│  ├─ 📄 indicators.py                       → 체크·라디오·스피너 화살표 이미지 생성
│  ├─ 📄 titlelogo.py                        → 언어·테마별 헤더 로고 로드
│  ├─ 📂 threads
│  │  ├─ 📄 __init__.py
│  │  ├─ 📄 setup_thread.py                  → yt-dlp & FFmpeg 자동 설치 (→ bin/)
│  │  ├─ 📄 series_parse_thread.py           → 시리즈 → 회차 목록 (키워드 제외 적용)
│  │  ├─ 📄 download_thread.py               → 다운로드 + 병합 + 자막 + 진행률 파싱
│  │  └─ 📄 conversion_thread.py             → 선택적 포맷/코덱 변환
│  └─ 📂 ui
│     ├─ 📄 __init__.py
│     └─ 📄 main_window_ui.py                → 메인 UI 구성 (헤더, 입력 바, 탭, 트레이)
├─ 📂 assets
│  ├─ 📂 fonts                                → Pretendard Variable / Pretendard JP / JetBrains Mono
│  ├─ 📂 icons                                → Fluent SVG 원본 19종 (빌드에는 미포함)
│  ├─ 📂 logo                                 → 헤더 로고 6종 (언어 3 × 테마 2)
│  └─ 🖼️ tver.ico                             → exe 아이콘
├─ 📂 tools
│  ├─ 📄 gen_icons.py                        → SVG → src/icons_data.py
│  ├─ 📄 gen_titlelogo.py                    → 로고 이미지 → assets/logo/
│  └─ 📄 font_preview.py                     → 글자 렌더링 옵션 비교 도구
├─ 🧾 실행 중 생성되는 항목
│  ├─ 📂 bin/                                 → yt-dlp.exe, ffmpeg.exe, ffprobe.exe (자동 설치)
│  ├─ 📄 downloader_config.json               → 사용자 설정
│  ├─ 📄 urlhistory.json                      → 다운로드 기록
│  ├─ 📄 favorites.json                       → 즐겨찾기 시리즈
│  ├─ 📂 thumbnails/                          → 썸네일 캐시
│  ├─ 📂 historybak/                          → 기록 백업
│  ├─ 📂 favoritbak/                          → 즐겨찾기 백업
│  └─ 📄 TVerDownloader_crash.log             → 크래시 로그
├─ 📄 .gitignore
├─ 📄 README.md
├─ 🖼️ logo.png
└─ 🖼️ main.png
```

---

## 🤝 기여 및 응원

- 버그 제보 및 코드 기여: [Issues](https://github.com/deuxdoom/TVerDownloader/issues)
- 상단의 [NordVPN 링크](https://refer-nordvpn.com/RRXwGuSQXTe) 로 가입시 개발자에게도 도움이 됩니다.
- 개발자 유투브: [YouTube 구독](https://www.youtube.com/@LE_SSERAFIM?sub_confirmation=1)
- Star 별 ⭐️을 눌러주시면 큰 힘이 됩니다.

---

## 📜 라이선스

[MIT License](https://opensource.org/licenses/MIT)
