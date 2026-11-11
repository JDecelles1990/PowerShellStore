<#
.SYNOPSIS
    Audits all local user accounts for lockout state, password age, expiration policy, and last logon activity.
.PSSTORE_META
    {
        "title": "Get Local Account & Password Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": []
    }
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

try {
    $results = @()
    $hasLocked = $false

    # Query local accounts via Get-LocalUser if cmdlet is available
    if (Get-Command -Name Get-LocalUser -ErrorAction SilentlyContinue) {
        $users = Get-LocalUser -ErrorAction Stop
        foreach ($u in $users) {
            $lastLog = if ($u.LastLogon) { $u.LastLogon.ToString("yyyy-MM-dd HH:mm") } else { "Never" }
            $pwdLastSet = if ($u.PasswordLastSet) { $u.PasswordLastSet } else { $null }
            $pwdAgeDays = if ($pwdLastSet) { [int]((Get-Date) - $pwdLastSet).TotalDays } else { -1 }

            if ($u.Enabled -and $u.LockedOut) {
                $hasLocked = $true
            }

            $results += [PSCustomObject]@{
                AccountName     = $u.Name
                Enabled         = [bool]$u.Enabled
                LockedOut       = [bool]$u.LockedOut
                PasswordExpires = [bool]$u.PasswordExpires
                PasswordAgeDays = if ($pwdAgeDays -ge 0) { $pwdAgeDays } else { "N/A" }
                LastLogon       = $lastLog
                Description     = if ($u.Description) { $u.Description } else { "No description" }
            }
        }
    }
    else {
        # Fallback using ADSI WinNT provider
        $computer = [ADSI]"WinNT://$env:COMPUTERNAME"
        $users = $computer.Children | Where-Object { $_.SchemaClassName -eq 'User' }
        foreach ($u in $users) {
            $flags = $u.UserFlags.Value
            $isDisabled = ($flags -band 2) -ne 0
            $isLocked = ($flags -band 16) -ne 0
            $pwdNeverExpires = ($flags -band 65536) -ne 0

            if (-not $isDisabled -and $isLocked) {
                $hasLocked = $true
            }

            $results += [PSCustomObject]@{
                AccountName     = [string]$u.Name
                Enabled         = (-not $isDisabled)
                LockedOut       = $isLocked
                PasswordExpires = (-not $pwdNeverExpires)
                PasswordAgeDays = "N/A"
                LastLogon       = try { $u.LastLogin.Value.ToString("yyyy-MM-dd HH:mm") } catch { "Never" }
                Description     = [string]$u.Description
            }
        }
    }

    # Human-readable table first
    $results | Format-Table -AutoSize | Out-String | Write-Output

    $statusOutcome = if ($hasLocked) { "warning" } else { "pass" }
    $summaryText = if ($hasLocked) {
        "Audited $($results.Count) local account(s). Warning: One or more active accounts are currently LOCKED OUT."
    } else {
        "Audited $($results.Count) local account(s). All active accounts are in good standing."
    }

    $payload = @{
        status  = $statusOutcome
        summary = $summaryText
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to audit local accounts: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
