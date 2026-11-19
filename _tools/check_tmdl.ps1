# Parse a TMDL semantic model folder with the same TMDL library Power BI Desktop uses.
# Usage: powershell -File check_tmdl.ps1 "<path to X.SemanticModel\definition>"
param([Parameter(Mandatory = $true)][string]$Folder)
$bin = (Get-AppxPackage Microsoft.MicrosoftPowerBIDesktop).InstallLocation + "\bin"
Add-Type -Path "$bin\Microsoft.PowerBI.Tabular.dll"
try {
    $db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder($Folder)
    $m = $db.Model
    "OK  tables=$($m.Tables.Count)  relationships=$($m.Relationships.Count)  expressions=$($m.Expressions.Count)"
    foreach ($t in $m.Tables) { "    $($t.Name): $($t.Columns.Count) columns, $($t.Measures.Count) measures" }
    exit 0
}
catch {
    "TMDL ERROR: " + $_.Exception.Message
    if ($_.Exception.InnerException) { "INNER: " + $_.Exception.InnerException.Message }
    exit 1
}
