<#
.SYNOPSIS
    Evaluates fixed disk volumes against a configurable free-space threshold for proactive capacity alerting.
.PSSTORE_META
    {
        "title": "Disk Free Space Report",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "LowSpaceThresholdPercent", "type": "int", "default": 15, "min": 1, "max": 90}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$LowSpaceThresholdPercent = 15
)

$ErrorActionPreference = 'Stop'

try {
    $drives = @()
    try {
        $cimDrives = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType = 3" -ErrorAction Stop
        foreach ($d in $cimDrives) {
            $totalGB = [math]::Round($d.Size / 1GB, 2)
            $freeGB = [math]::Round($d.FreeSpace / 1GB, 2)
            $percentFree = if ($totalGB -gt 0) { [math]::Round(($freeGB / $totalGB) * 100, 1) } else { 0 }
            $drives += [PSCustomObject]@{
                DeviceID     = $d.DeviceID
                VolumeName   = $d.VolumeName
                TotalGB      = $totalGB
                FreeGB       = $freeGB
                PercentFree  = $percentFree
                LowDiskSpace = ($percentFree -lt $LowSpaceThresholdPercent)
            }
        }
    } catch {
        # Resilient fallback to .NET DriveInfo (works without CIM/WMI service access)
        $netDrives = [System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' -and $_.IsReady }
        foreach ($d in $netDrives) {
            $totalGB = [math]::Round($d.TotalSize / 1GB, 2)
            $freeGB = [math]::Round($d.TotalFreeSpace / 1GB, 2)
            $percentFree = if ($totalGB -gt 0) { [math]::Round(($freeGB / $totalGB) * 100, 1) } else { 0 }
            $drives += [PSCustomObject]@{
                DeviceID     = $d.Name.TrimEnd('\')
                VolumeName   = $d.VolumeLabel
                TotalGB      = $totalGB
                FreeGB       = $freeGB
                PercentFree  = $percentFree
                LowDiskSpace = ($percentFree -lt $LowSpaceThresholdPercent)
            }
        }
    }

    $lowDrives = @($drives | Where-Object { $_.LowDiskSpace -eq $true })
    $hasLow = $lowDrives.Count -gt 0

    $status = if ($hasLow) { "warning" } else { "pass" }
    $summary = if ($hasLow) {
        "WARNING: $($lowDrives.Count) drive(s) below ${LowSpaceThresholdPercent}% threshold ($($lowDrives.DeviceID -join ', '))."
    } else {
        "All $(@($drives).Count) fixed drive(s) have healthy free capacity (>= ${LowSpaceThresholdPercent}%)."
    }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($drives)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Disk space query failed: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
