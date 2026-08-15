<#
.SYNOPSIS
빌드된 TVerDownloader.exe 창을 PNG로 찍는다.

.DESCRIPTION
개발 실행은 QWidget.grab()으로 충분하지만 exe는 밖에서 찍어야 한다.
PrintWindow를 쓰는 이유는 창이 가려져 있어도 찍히기 때문이고,
SetProcessDPIAware를 먼저 부르는 이유는 그러지 않으면 150% 배율에서
GetWindowRect가 축소된 좌표를 돌려줘 오른쪽이 잘리기 때문이다.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools/capture_window.ps1 -Out shot.png
#>
param([Parameter(Mandatory = $true)][string]$Out)

Add-Type @"
using System;
using System.Drawing;
using System.Runtime.InteropServices;
public class Cap {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static IntPtr Found = IntPtr.Zero;
  public static uint Target = 0;
  public static bool Walk(IntPtr h, IntPtr p) {
    uint pid; GetWindowThreadProcessId(h, out pid);
    if (pid == Target && IsWindowVisible(h) && GetWindowTextLength(h) > 0) { Found = h; return false; }
    return true;
  }
  public static Bitmap Shot(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    var bmp = new Bitmap(r.R - r.L, r.B - r.T);
    using (var g = Graphics.FromImage(bmp)) {
      IntPtr hdc = g.GetHdc();
      PrintWindow(h, hdc, 2);
      g.ReleaseHdc(hdc);
    }
    return bmp;
  }
}
"@ -ReferencedAssemblies System.Drawing, System.Windows.Forms

[Cap]::SetProcessDPIAware() | Out-Null

$proc = Get-Process TVerDownloader -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { Write-Output "NO PROCESS"; exit 1 }

[Cap]::Target = $proc.Id
[Cap]::Found = [IntPtr]::Zero
[Cap]::EnumWindows([Cap+EnumProc] { param($h, $p) return [Cap]::Walk($h, $p) }, [IntPtr]::Zero) | Out-Null

$h = [Cap]::Found
if ($h -eq [IntPtr]::Zero) { Write-Output "NO WINDOW"; exit 1 }

[Cap]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 300
$bmp = [Cap]::Shot($h)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output "SAVED $Out $($bmp.Width)x$($bmp.Height)"
