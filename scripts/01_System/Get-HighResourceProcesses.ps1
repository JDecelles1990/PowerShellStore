<#
.SYNOPSIS
    Identifies top processes consuming excessive CPU or RAM on the local workstation.
.PSSTORE_META
    {
        "title": "Get High-Resource Processes",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "SortBy", "type": "string", "default": "CPU"},
            {"name": "TopCount", "type": "int", "default": 10, "min": 1, "max": 50}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$SortBy = "CPU",

    [Parameter(Mandatory = $false)]
    [int]$TopCount = 10
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$topList = @()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Validate parameters
    if ($SortBy -notmatch '^(CPU|Memory)$') {
        $SortBy = "CPU"
    }
    $TopCount = [math]::Max(1, [math]::Min(50, $TopCount))

    $allProcesses = Get-Process -ErrorAction Stop

    $results = [System.Collections.Generic.List[PSObject]]::new()
    foreach ($proc in $allProcesses) {
        $wsMb = [math]::Round($proc.WorkingSet64 / 1MB, 2)
        $pmMb = [math]::Round($proc.PrivateMemorySize64 / 1MB, 2)
        $cpuSec = if ($proc.CPU) { [math]::Round($proc.CPU, 2) } else { 0.0 }

        $procPath = "N/A"
        $company = "Unknown"
        try {
            if ($proc.Path) {
                $procPath = $proc.Path
                if ($proc.Company) { $company = $proc.Company }
            }
        }
        catch {
            # System / protected process path not accessible without elevation
            $procPath = "Access Denied (System/Protected)"
        }

        $results.Add([PSCustomObject]@{
            ProcessName  = $proc.ProcessName
            PID          = $proc.Id
            WorkingSetMB = $wsMb
            PrivateMemMB = $pmMb
            CPUSec       = $cpuSec
            Company      = $company
            Path         = $procPath
        })
    }

    # Sort results
    if ($SortBy -eq "Memory") {
        $topList = @($results | Sort-Object -Property WorkingSetMB -Descending | Select-Object -First $TopCount)
    }
    else {
        $topList = @($results | Sort-Object -Property CPUSec -Descending | Select-Object -First $TopCount)
    }

    # Human-readable table first for terminal / RMM
    if ($topList.Count -gt 0) {
        $tableOutput = $topList | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }

    $summary = "Retrieved top $($topList.Count) resource-consuming processes sorted by $SortBy."
}
catch {
    $status = "error"
    $summary = "Failed to query process metrics: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($topList)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
