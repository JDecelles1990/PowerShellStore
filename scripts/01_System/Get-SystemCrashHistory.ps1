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

try {
    $cutoffDate = (Get-Date).AddDays(-$MaxDays)
    $results = @()

    # 1. Inspect Windows Minidump files
    $minidumpDir = "$env:SystemRoot\Minidump"
    if (Test-Path $minidumpDir) {
        $dumpFiles = Get-ChildItem -Path $minidumpDir -Filter "*.dmp" -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $cutoffDate } |
            Sort-Object LastWriteTime -Descending

        foreach ($dump in $dumpFiles) {
            $sizeKb = [math]::Round($dump.Length / 1KB, 1)
            $results += [PSCustomObject]@{
                Timestamp    = $dump.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                Source       = "Minidump File"
                EventOrCode  = "MEMORY.DMP"
                Details      = "Size: $sizeKb KB"
                FilePath     = $dump.FullName
            }
        }
    }

    # 2. Inspect System Event Log for BugCheck (1001) and Kernel-Power (41)
    $events = Get-WinEvent -FilterHashtable @{
        LogName   = 'System'
        Id        = @(41, 1001)
        StartTime = $cutoffDate
    } -MaxEvents 50 -ErrorAction SilentlyContinue

    if ($events) {
        foreach ($evt in $events) {
            $src = if ($evt.Id -eq 1001) { "BugCheck (BSOD)" } else { "Kernel-Power (Unclean Reboot)" }
            $cleanMsg = ($evt.Message -replace '\s+', ' ').Trim()
            if ($cleanMsg.Length -gt 120) {
                $cleanMsg = $cleanMsg.Substring(0, 117) + "..."
            }

            $results += [PSCustomObject]@{
                Timestamp    = $evt.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                Source       = $src
                EventOrCode  = "Event ID $($evt.Id)"
                Details      = $cleanMsg
                FilePath     = "EventLog: System"
            }
        }
    }

    # Sort all by Timestamp descending
    $sortedResults = @($results | Sort-Object Timestamp -Descending)

    if ($sortedResults.Count -eq 0) {
        Write-Output "No system crash dumps or BSOD events detected in the last $MaxDays day(s)."
        $payload = @{
            status  = "pass"
            summary = "System is healthy: 0 BSOD crashes or minidumps detected in the past $MaxDays day(s)."
            data    = @()
            errors  = @()
        }
    }
    else {
        # Human-readable table first
        $sortedResults | Format-Table -AutoSize | Out-String | Write-Output

        $payload = @{
            status  = "warning"
            summary = "Found $($sortedResults.Count) crash/unclean shutdown event(s) in the past $MaxDays day(s)."
            data    = @($sortedResults)
            errors  = @()
        }
    }

    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to inspect system crash history: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

