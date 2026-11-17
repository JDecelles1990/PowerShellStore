<#
.SYNOPSIS
    Audits BSOD minidumps and kernel crash event records over a configurable lookback window.
.PSSTORE_META
    {
        "title": "Get System Crash & BSOD History",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "MaxDays", "type": "int", "default": 30, "min": 1, "max": 90}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$MaxDays = 30
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$sortedResults = @()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $MaxDays = [math]::Max(1, [math]::Min(90, $MaxDays))
    $cutoffDate = (Get-Date).AddDays(-$MaxDays)
    $results = [System.Collections.Generic.List[PSObject]]::new()

    # 1. Inspect Windows Minidump files
    $minidumpDir = "$env:SystemRoot\Minidump"
    if (Test-Path -Path $minidumpDir -ErrorAction Stop) {
        $dumpFiles = Get-ChildItem -Path $minidumpDir -Filter "*.dmp" -ErrorAction Stop |
            Where-Object { $_.LastWriteTime -ge $cutoffDate } |
            Sort-Object LastWriteTime -Descending

        foreach ($dump in $dumpFiles) {
            $sizeKb = [math]::Round($dump.Length / 1KB, 1)
            $results.Add([PSCustomObject]@{
                Timestamp   = $dump.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                Source      = "Minidump File"
                EventOrCode = "MEMORY.DMP"
                Details     = "Size: $sizeKb KB"
                FilePath    = $dump.FullName
            })
        }
    }

    # 2. Inspect System Event Log for BugCheck (1001) and Kernel-Power (41)
    $events = @()
    try {
        $events = Get-WinEvent -FilterHashtable @{
            LogName   = 'System'
            Id        = @(41, 1001)
            StartTime = $cutoffDate
        } -MaxEvents 50 -ErrorAction Stop
    }
    catch {
        if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound') {
            throw
        }
    }

    if ($events) {
        foreach ($evt in $events) {
            $src = if ($evt.Id -eq 1001) { "BugCheck (BSOD)" } else { "Kernel-Power (Unclean Reboot)" }
            $cleanMsg = ($evt.Message -replace '\s+', ' ').Trim()
            if ($cleanMsg.Length -gt 120) {
                $cleanMsg = $cleanMsg.Substring(0, 117) + "..."
            }

            $results.Add([PSCustomObject]@{
                Timestamp   = $evt.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                Source      = $src
                EventOrCode = "Event ID $($evt.Id)"
                Details     = $cleanMsg
                FilePath    = "EventLog: System"
            })
        }
    }

    # Sort all by Timestamp descending
    $sortedResults = @($results | Sort-Object -Property Timestamp -Descending)

    if ($sortedResults.Count -eq 0) {
        $status = "pass"
        $summary = "System is healthy: 0 BSOD crashes or minidumps detected in the past $MaxDays day(s)."
        Write-Output "No system crash dumps or BSOD events detected in the last $MaxDays day(s)."
    }
    else {
        # Human-readable table first
        $tableOutput = $sortedResults | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""

        $status = "warning"
        $summary = "Found $($sortedResults.Count) crash/unclean shutdown event(s) in the past $MaxDays day(s)."
    }
}
catch {
    $status = "error"
    $summary = "Failed to inspect system crash history: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($sortedResults)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
