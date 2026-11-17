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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $HoursBack = [math]::Max(1, [math]::Min(168, $HoursBack))
    $MaxEvents = [math]::Max(5, [math]::Min(100, $MaxEvents))
    $startTime = (Get-Date).AddHours(-$HoursBack)

    # Filter for Error (2) and Critical (1) in System and Application logs
    $filter = @{
        LogName   = @('System', 'Application')
        Level     = @(1, 2)
        StartTime = $startTime
    }

    $rawEvents = @()
    try {
        $rawEvents = Get-WinEvent -FilterHashtable $filter -MaxEvents $MaxEvents -ErrorAction Stop
    }
    catch {
        if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound') {
            throw
        }
    }

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

            $results.Add([PSCustomObject]@{
                    TimeCreated  = $evt.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                    LogName      = $evt.LogName
                    Level        = $levelName
                    EventID      = $evt.Id
                    ProviderName = $evt.ProviderName
                    Message      = if ($cleanMessage) { $cleanMessage } else { "(No description)" }
                })
        }
    }

    if ($results.Count -eq 0) {
        $status = "pass"
        $summary = "Clean logs: 0 Critical or Error events logged in the past $HoursBack hour(s)."
        Write-Output $summary
    }
    else {
        # Human-readable table first
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""

        $status = "warning"
        $summary = "Retrieved $($results.Count) recent Critical/Error event(s) from the past $HoursBack hour(s)."
    }
}
catch {
    $status = "error"
    $summary = "Failed to query Windows Event Log: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($results)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
