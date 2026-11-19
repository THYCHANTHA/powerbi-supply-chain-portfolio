# Open a .pbip in Power BI Desktop, refresh it, run DAX tests and screenshot every page.
# Usage: powershell -File open_and_test.ps1 -Pbip "...\X.pbip" -Title "X" -QueryFile tests.dax -ShotDir dir -Pages "Page A|Page B"
param([string]$Pbip, [string]$Title, [string]$QueryFile, [string]$ShotDir, [string]$Pages)
$tools = Split-Path -Parent $MyInvocation.MyCommand.Path
$before = @(Get-Process PBIDesktop -ErrorAction SilentlyContinue | ForEach-Object Id)
Start-Process -FilePath "$env:LOCALAPPDATA\Microsoft\WindowsApps\PBIDesktopStore.exe" -ArgumentList "`"$Pbip`""

$deadline = (Get-Date).AddSeconds(240); $proc = $null; $port = $null
while ((Get-Date) -lt $deadline -and -not $port) {
    Start-Sleep -Seconds 3
    $proc = Get-Process PBIDesktop -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id -and $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
    if ($proc) {
        $ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($proc.Id)"
        if ($ms) {
            $dir = ($ms.CommandLine -replace '.*-s\s+"([^"]+)".*', '$1')
            $pf = Join-Path $dir "msmdsrv.port.txt"
            if (Test-Path $pf) { $port = [IO.File]::ReadAllText($pf, [Text.Encoding]::Unicode).Trim() }
        }
    }
}
if (-not $port) { "could not find engine port"; exit 1 }
"PBIDesktop pid=$($proc.Id) port=$port"
Start-Sleep -Seconds 8
& "$tools\test_model.ps1" -Port $port -QueryFile $QueryFile -Refresh
Start-Sleep -Seconds 6

& "$tools\shoot_pages.ps1" -Title $Title -ShotDir $ShotDir -Pages $Pages
