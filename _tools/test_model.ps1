# Refresh the model open in Power BI Desktop and run DAX test queries against it.
# Usage: powershell -File test_model.ps1 -Port 12345 -QueryFile tests.dax [-Refresh]
# tests.dax: queries separated by a line containing only ---
param([int]$Port, [string]$QueryFile, [switch]$Refresh)
$bin = (Get-AppxPackage Microsoft.MicrosoftPowerBIDesktop).InstallLocation + "\bin"
Add-Type -Path "$bin\Microsoft.PowerBI.Tabular.dll"
Add-Type -Path "$bin\Microsoft.PowerBI.AdomdClient.dll"

if ($Refresh) {
    $srv = New-Object Microsoft.AnalysisServices.Tabular.Server
    $srv.Connect("Data Source=localhost:$Port")
    $db = $srv.Databases[0]
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $db.Model.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
    $res = $db.Model.SaveChanges()
    "refresh done in $([int]$sw.Elapsed.TotalSeconds)s"
    foreach ($t in $db.Model.Tables) {
        foreach ($p in $t.Partitions) { if ($p.State -ne 'Ready') { "PARTITION $($t.Name): $($p.State) $($p.ErrorMessage)" } }
    }
    $srv.Disconnect()
}

$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$conn.Open()
$queries = ([IO.File]::ReadAllText($QueryFile)) -split "(?m)^---\s*$"
foreach ($qtext in $queries) {
    $qtext = $qtext.Trim(); if (-not $qtext) { continue }
    "=== " + ($qtext -split "`n")[0]
    try {
        $cmd = $conn.CreateCommand(); $cmd.CommandText = $qtext
        $r = $cmd.ExecuteReader()
        $names = 0..($r.FieldCount - 1) | ForEach-Object { $r.GetName($_) -replace '^.*\[|\]$', '' }
        $names -join " | "
        $n = 0
        while ($r.Read() -and $n -lt 25) {
            (0..($r.FieldCount - 1) | ForEach-Object { $v = $r.GetValue($_); if ($v -is [double]) { [math]::Round($v, 4) } else { $v } }) -join " | "
            $n++
        }
        $r.Close()
    } catch { "DAX ERROR: " + $_.Exception.Message }
}
$conn.Close()
