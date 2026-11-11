<#
.SYNOPSIS
    Clears stuck print jobs and restarts the Print Spooler service.
.PSSTORE_META
    {
        "title": "Reset Print Spooler",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 30,
        "output_mode": "text",
        "params": [
            {"name": "ClearQueueFiles", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$ClearQueueFiles = $true
)

$ErrorActionPreference = 'Stop'

try {
    Stop-Service -Name Spooler -Force -ErrorAction Stop
    if ($ClearQueueFiles) {
        $spoolPath = "$env:SystemRoot\System32\spool\PRINTERS\*"
        Remove-Item -Path $spoolPath -Force -ErrorAction Stop
    }
    Start-Service -Name Spooler -ErrorAction Stop
    Write-Output "[SUCCESS] Print Spooler restarted. Queue cleared: $ClearQueueFiles"
}
catch {
    Write-Error "[ERROR] Failed to reset Print Spooler: $($_.Exception.Message)"
    exit 1
}
finally {
    # Ensure service status is always reported for RMM activity logs
    Get-Service -Name Spooler | Select-Object Name, Status, StartType
}

