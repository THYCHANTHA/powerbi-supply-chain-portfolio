# Save an open Power BI Desktop project (Ctrl+S) so the loaded data cache is kept, then close it.
# Usage: powershell -File save_and_close.ps1 -Title "X" -ProjectDir "...\folder with X.pbip"
param([string]$Title, [string]$ProjectDir)
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W2 { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@
$p = Get-Process PBIDesktop | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if (-not $p) { "window not found"; exit 1 }
[void][W2]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait("^s")
$cache = Get-ChildItem $ProjectDir -Recurse -Filter cache.abf -ErrorAction SilentlyContinue
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $cache = Get-ChildItem $ProjectDir -Recurse -Filter cache.abf -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-2) }
    if ($cache) { break }
}
if ($cache) { "saved: $($cache.FullName) ($([int]($cache.Length/1KB)) KB)" } else { "WARNING: no fresh cache.abf found; not closing"; exit 1 }
Start-Sleep -Seconds 3
Stop-Process -Id $p.Id -Force
"closed $($p.Id)"
