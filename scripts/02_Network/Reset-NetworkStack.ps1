<#
.SYNOPSIS
    Flushes DNS caches, releases and renews DHCP leases, and resets the Winsock catalog and TCP/IP stack to resolve connectivity dropouts.
.PSSTORE_META
    {
        "title": "Reset Network Stack & Flush DNS",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 60,
        "output_mode": "json",
        "params": [
            {"name": "FlushDNS", "type": "bool", "default": true},
            {"name": "RenewDHCP", "type": "bool", "default": true},
            {"name": "ResetWinsock", "type": "bool", "default": true},
            {"name": "ResetTCPStack", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$FlushDNS = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RenewDHCP = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ResetWinsock = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ResetTCPStack = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$actionRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$rebootRecommended = $false

function Execute-NetCommand {
    param(
        [string]$ActionName,
        [scriptblock]$ScriptBlock
    )
    try {
        $output = & $ScriptBlock 2>&1 | Out-String
        $actionRecords.Add([PSCustomObject]@{
            Action      = $ActionName
            Status      = "Success"
            Details     = ($output.Trim() -replace '\s+', ' ')
        })
    }
    catch {
        $actionRecords.Add([PSCustomObject]@{
            Action      = $ActionName
            Status      = "Warning/Failed"
            Details     = $_.Exception.Message
        })
        $errors.Add("$ActionName failed: $($_.Exception.Message)")
    }
}

try {
    # 1. Flush & Register DNS
    if ($FlushDNS) {
        Execute-NetCommand -ActionName "Flush DNS Cache" -ScriptBlock {
            & ipconfig.exe /flushdns
        }
        Execute-NetCommand -ActionName "Register DNS" -ScriptBlock {
            & ipconfig.exe /registerdns
        }
    }

    # 2. Release & Renew DHCP Leases
    if ($RenewDHCP) {
        Execute-NetCommand -ActionName "Release DHCP Leases" -ScriptBlock {
            & ipconfig.exe /release
        }
        Start-Sleep -Seconds 1
        Execute-NetCommand -ActionName "Renew DHCP Leases" -ScriptBlock {
            & ipconfig.exe /renew
        }
    }

    # 3. Reset Winsock Catalog
    if ($ResetWinsock) {
        Execute-NetCommand -ActionName "Reset Winsock Catalog" -ScriptBlock {
            & netsh.exe winsock reset
        }
        $rebootRecommended = $true
    }

    # 4. Reset TCP/IP Stack
    if ($ResetTCPStack) {
        Execute-NetCommand -ActionName "Reset TCP/IP Stack" -ScriptBlock {
            $logPath = Join-Path -Path $env:TEMP -ChildPath "netsh_resetlog.txt"
            & netsh.exe int ip reset $logPath
        }
        $rebootRecommended = $true
    }

    $failedActions = ($actionRecords | Where-Object { $_.Status -ne "Success" }).Count
    if ($failedActions -gt 0) {
        $status = "warning"
        $summary = "Network stack reset completed with $failedActions warning(s)."
    } else {
        $status = "pass"
        $summary = "Network stack reset successfully." + $(if ($rebootRecommended) { " System reboot is recommended to finalize Winsock/TCP changes." } else { "" })
    }

    # Human-Readable ASCII Table Output
    if ($actionRecords.Count -gt 0) {
        $tableOutput = $actionRecords | Format-Table -Property Action, Status, Details -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Failed to reset network stack: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status             = $status
        summary            = $summary
        reboot_recommended = $rebootRecommended
        data               = @($actionRecords)
        errors             = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
