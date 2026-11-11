<#
.SYNOPSIS
    Checks Windows registry and system indicators to determine if an endpoint requires a pending reboot.
.PSSTORE_META
    {
        "title": "Check Pending Reboot Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": []
    }
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

try {
    $cbsReboot = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
    $wuReboot = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
    
    $fileRename = $false
    try {
        $sessionMan = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name "PendingFileRenameOperations" -ErrorAction SilentlyContinue
        if ($sessionMan -and $sessionMan.PendingFileRenameOperations) {
            $fileRename = $true
        }
    } catch {
        $fileRename = $false
    }

    $computerRename = $false
    try {
        $activeName = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName" -Name "ComputerName" -ErrorAction SilentlyContinue).ComputerName
        $configName = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName" -Name "ComputerName" -ErrorAction SilentlyContinue).ComputerName
        if ($activeName -and $configName -and ($activeName -ne $configName)) {
            $computerRename = $true
        }
    } catch {
        $computerRename = $false
    }

    $isRebootPending = $cbsReboot -or $wuReboot -or $fileRename -or $computerRename

    $status = if ($isRebootPending) { "warning" } else { "pass" }
    $summary = if ($isRebootPending) {
        "Reboot IS PENDING on this endpoint."
    } else {
        "No pending reboot detected. System is clean."
    }

    $details = [PSCustomObject]@{
        IsRebootPending            = $isRebootPending
        ComponentBasedServicing    = $cbsReboot
        WindowsUpdate              = $wuReboot
        PendingFileRenameOperation = $fileRename
        ComputerNameChange         = $computerRename
    }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($details)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Failed to query reboot indicators: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}

