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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $cbsReboot = Test-Path -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending" -ErrorAction Stop
    $wuReboot = Test-Path -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired" -ErrorAction Stop

    $fileRename = $false
    try {
        $sessionMan = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name "PendingFileRenameOperations" -ErrorAction Stop
        if ($sessionMan -and $sessionMan.PendingFileRenameOperations) {
            $fileRename = $true
        }
    }
    catch {
        $fileRename = $false
    }

    $computerRename = $false
    try {
        $activeName = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName" -Name "ComputerName" -ErrorAction Stop).ComputerName
        $configName = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName" -Name "ComputerName" -ErrorAction Stop).ComputerName
        if ($activeName -and $configName -and ($activeName -ne $configName)) {
            $computerRename = $true
        }
    }
    catch {
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
    $results.Add($details)

    # Human-readable table before JSON envelope
    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Failed to query reboot indicators: $($_.Exception.Message)"
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
