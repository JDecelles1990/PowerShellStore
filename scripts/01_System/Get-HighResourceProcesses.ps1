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

try {
    # Validate SortBy parameter
    if ($SortBy -notmatch '^(CPU|Memory)$') {
        $SortBy = "CPU"
    }

    $allProcesses = Get-Process -ErrorAction Stop

    $results = @()
    foreach ($proc in $allProcesses) {
        $wsMb = [math]::Round($proc.WorkingSet64 / 1MB, 2)
        $pmMb = [math]::Round($proc.PrivateMemorySize64 / 1MB, 2)
        $cpuSec = if ($proc.CPU) { [math]::Round($proc.CPU, 2) } else { 0.0 }

        $procPath = "N/A"
        $company = "N/A"
        try {
            if ($proc.Path) {
                $procPath = $proc.Path
                $company = $proc.Company
            }
        }
        catch {
            # System / protected process path not accessible without elevation
            $procPath = "Access Denied (System/Protected)"
        }

        $results += [PSCustomObject]@{
            ProcessName  = $proc.ProcessName
            PID          = $proc.Id
            WorkingSetMB = $wsMb
            PrivateMemMB = $pmMb
            CPUSec       = $cpuSec
            Company      = if ($company) { $company } else { "Unknown" }
            Path         = $procPath
        }
    }

    # Sort results
    if ($SortBy -eq "Memory") {
        $topList = $results | Sort-Object WorkingSetMB -Descending | Select-Object -First $TopCount
    }
    else {
        $topList = $results | Sort-Object CPUSec -Descending | Select-Object -First $TopCount
    }

    # Human-readable table first for terminal / RMM
    $topList | Format-Table -AutoSize | Out-String | Write-Output

    $payload = @{
        status  = "pass"
        summary = "Retrieved top $TopCount resource-consuming processes sorted by $SortBy."
        data    = @($topList)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query process metrics: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
