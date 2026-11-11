<#
.SYNOPSIS
    Aggregates Critical and Error events from System and Application logs over a recent time window.
.PSSTORE_META
    {
        "title": "Get Recent Event Log Errors",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "HoursBack", "type": "int", "default": 24, "min": 1, "max": 168},
            {"name": "MaxEvents", "type": "int", "default": 30, "min": 5, "max": 100}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$HoursBack = 24,

    [Parameter(Mandatory = $false)]
    [int]$MaxEvents = 30
)

$ErrorActionPreference = 'Stop'

try {
    $startTime = (Get-Date).AddHours(-$HoursBack)

    # Filter for Error (2) and Critical (1) in System and Application logs
    $filter = @{
        LogName   = @('System', 'Application')
        Level     = @(1, 2)
        StartTime = $startTime
    }

    $rawEvents = Get-WinEvent -FilterHashtable $filter -MaxEvents $MaxEvents -ErrorAction SilentlyContinue

    $results = @()
    if ($rawEvents) {
        foreach ($evt in $rawEvents) {
            $levelName = switch ($evt.Level) {
                1 { "Critical" }
                2 { "Error" }
                default { "Unknown" }
            }

            $cleanMessage = ($evt.Message -replace '\s+', ' ').Trim()
            if ($cleanMessage.Length -gt 150) {
                $cleanMessage = $cleanMessage.Substring(0, 147) + "..."
            }

            $results += [PSCustomObject]@{
                TimeCreated  = $evt.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                LogName      = $evt.LogName
                Level        = $levelName
                EventID      = $evt.Id
                ProviderName = $evt.ProviderName
                Message      = if ($cleanMessage) { $cleanMessage } else { "(No description)" }
            }
        }
    }

    if ($results.Count -eq 0) {
        Write-Output "No Critical or Error events found across System/Application logs in the last $HoursBack hour(s)."
        $payload = @{
            status  = "pass"
            summary = "Clean logs: 0 Critical or Error events logged in the past $HoursBack hour(s)."
            data    = @()
            errors  = @()
        }
    }
    else {
        # Human-readable table first
        $results | Format-Table -AutoSize | Out-String | Write-Output

        $payload = @{
            status  = "warning"
            summary = "Retrieved $($results.Count) recent Critical/Error event(s) from the past $HoursBack hour(s)."
            data    = @($results)
            errors  = @()
        }
    }

    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query Windows Event Log: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
