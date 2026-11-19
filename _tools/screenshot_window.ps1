# Bring a window (by title text) to the front and save a screenshot of it.
# Usage: powershell -File screenshot_window.ps1 -Title "Supply Chain Performance" -Out shot.png
param([string]$Title, [string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[void][W]::SetProcessDPIAware()
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if (-not $p) { "window not found"; exit 1 }
[void][W]::ShowWindow($p.MainWindowHandle, 3)   # maximize
[void][W]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Seconds 2
$r = New-Object W+RECT
[void][W]::GetWindowRect($p.MainWindowHandle, [ref]$r)
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
"saved $Out ($w x $h)"
