# Select each report page tab in an open Power BI Desktop window (UI Automation) and screenshot it.
# Usage: powershell -File shoot_pages.ps1 -Title "X" -ShotDir dir -Pages "Page A|Page B"
param([string]$Title, [string]$ShotDir, [string]$Pages)
$tools = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process PBIDesktop | Where-Object { $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
$root = [Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$i = 0
foreach ($pg in ($Pages -split '\|')) {
    $i++
    $cond = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty, $pg)
    $els = $root.FindAll([Windows.Automation.TreeScope]::Descendants, $cond)
    $ok = $false
    foreach ($el in $els) {
        foreach ($pat in $el.GetSupportedPatterns()) {
            if ($pat.ProgrammaticName -like "*SelectionItem*") { $el.GetCurrentPattern($pat).Select(); $ok = $true; break }
            if ($pat.ProgrammaticName -like "*Invoke*") { $el.GetCurrentPattern($pat).Invoke(); $ok = $true; break }
        }
        if ($ok) { break }
    }
    if (-not $ok) { "page tab '$pg' not selectable (found $($els.Count))" }
    Start-Sleep -Seconds 6
    & "$tools\screenshot_window.ps1" -Title $Title -Out (Join-Path $ShotDir ("{0}_{1}.png" -f ($Title -replace '\W', ''), $i))
}
