<#
.SYNOPSIS
    버전을 낮춘 시험용 빌드를 따로 만든다. 자동 업데이트를 실제 릴리스로 검증할 때 쓴다.

.DESCRIPTION
    GitHub 릴리스가 v3.2.0이므로, 그보다 낮은 버전으로 빌드해야 업데이트가 걸린다.
    이 스크립트는 TVerDownloader.py의 APP_VERSION만 잠시 낮춰 빌드하고 곧바로 되돌린다.

    산출물은 dist/가 아니라 별도 폴더에 복사한다. 평소 쓰는 dist/TVerDownloader가
    시험 도중 3.2.0으로 덮여 버리는 것을 막기 위해서다. 시험이 끝나면 그 폴더만
    지우면 원래대로다.

    빌드는 spec이 정한 대로 dist/로 나가므로, 복사한 뒤 dist/를 원래 버전으로 한 번
    더 빌드한다. 이걸 빠뜨리면 dist/에 낮춘 버전이 남아 그대로 배포될 수 있다.

    실제로 파일이 바뀌는 시험이므로, 끝나고 나면 시험 폴더의 exe는 v3.2.0이 된다.
    그게 성공의 증거다.

.PARAMETER Version
    빌드에 넣을 가짜 버전. 기본 3.1.0 (릴리스 v3.2.0보다 낮아야 한다).

.PARAMETER OutDir
    시험용 사본을 둘 폴더. 기본 dist-updatetest.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/make_update_test_build.ps1

.NOTES
    PyInstaller는 진행 상황을 stderr로 내보낸다. ErrorActionPreference가 Stop인
    채로 부르면 그 줄들이 오류로 잡혀 빌드가 멀쩡해도 실패로 끝난다. 그래서 그
    호출 동안만 Continue로 내린다.
#>
param(
    [string]$Version = "3.1.0",
    [string]$OutDir = "dist-updatetest"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$entry = Join-Path $root "TVerDownloader.py"
$backup = Join-Path $env:TEMP ("TVerDownloader.py.bak-" + [guid]::NewGuid().ToString("N"))

Write-Host ""
Write-Host "  버전을 낮춘 시험용 빌드" -ForegroundColor Cyan
Write-Host "  ================================================"
Write-Host "  가짜 버전 : $Version"
Write-Host "  출력 폴더 : $OutDir"
Write-Host ""

Get-Process TVerDownloader -ErrorAction SilentlyContinue | Stop-Process -Force
Copy-Item $entry $backup

try {
    $text = Get-Content $entry -Raw -Encoding UTF8
    $patched = [regex]::Replace($text, 'APP_VERSION = "[^"]+"', "APP_VERSION = `"$Version`"", 1)
    if ($patched -eq $text) { throw "APP_VERSION 줄을 찾지 못했습니다." }
    Set-Content $entry $patched -Encoding UTF8 -NoNewline

    Write-Host "  빌드 중... (1~2분)" -ForegroundColor Yellow
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & py -3.14 -m PyInstaller TVerDownloader.spec --noconfirm --clean 2>&1 | Out-Null
    $buildCode = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($buildCode -ne 0) { throw "빌드에 실패했습니다." }
}
finally {
    Copy-Item $backup $entry -Force
    Remove-Item $backup -Force -ErrorAction SilentlyContinue
    Write-Host "  TVerDownloader.py를 원래 버전으로 되돌렸습니다." -ForegroundColor DarkGray
}

$target = Join-Path $root $OutDir
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Copy-Item (Join-Path $root "dist\TVerDownloader") $target -Recurse

Write-Host "  dist/ 를 원래 버전으로 다시 빌드합니다..." -ForegroundColor Yellow
$previous = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& py -3.14 -m PyInstaller TVerDownloader.spec --noconfirm --clean 2>&1 | Out-Null
$restoreCode = $LASTEXITCODE
$ErrorActionPreference = $previous
if ($restoreCode -ne 0) {
    Write-Host "  [주의] dist/ 재빌드에 실패했습니다. dist/ 에 $Version 빌드가 남아 있습니다." -ForegroundColor Red
    Write-Host "         직접 다시 빌드해 주세요: py -3.14 -m PyInstaller TVerDownloader.spec --noconfirm --clean" -ForegroundColor Red
}

Write-Host ""
Write-Host "  준비됐습니다." -ForegroundColor Green
Write-Host ""
Write-Host "  1) 아래 명령으로 실행합니다(작업 디렉터리 지정이 중요합니다):"
Write-Host "       Start-Process -FilePath `"$target\TVerDownloader.exe`" -WorkingDirectory `"$target`""
Write-Host ""
Write-Host "  2) 잠시 뒤 '새 버전 v3.2.0' 안내가 뜹니다. [지금 업데이트]를 누릅니다."
Write-Host "  3) 받기가 끝나면 프로그램이 닫히고 검은 창이 떠 교체를 진행합니다."
Write-Host "  4) 다시 뜬 프로그램의 제목이 v3.2.0이면 성공입니다."
Write-Host ""
Write-Host "  확인해 볼 것:"
Write-Host "    - $OutDir\bin, downloader_config.json 이 그대로 남아 있는가"
Write-Host "    - $OutDir\update-workspace 가 다시 켜질 때 지워졌는가"
Write-Host "    - 카스퍼스키가 update.cmd 나 cmd.exe 를 막지 않았는가"
Write-Host ""
Write-Host "  되돌리려면 $OutDir 폴더를 지우면 됩니다. dist/ 는 원래 버전으로 다시 빌드해 두었습니다."
Write-Host ""
