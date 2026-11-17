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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $hasLocked = $false

    # Helper: read real SAM lockout flag via ADSI since PS 5.1 LocalUser lacks LockedOut
    $getLockoutState = {
        param([string]$AccountName)
        try {
            $adsiObj = [ADSI]"WinNT://$env:COMPUTERNAME/$AccountName,user"
            $flags = [int]$adsiObj.UserFlags.Value
            return (($flags -band 16) -ne 0)
        }
        catch {
            return $false
        }
    }

    # Query local accounts via Get-LocalUser if cmdlet is available
    if (Get-Command -Name Get-LocalUser -ErrorAction SilentlyContinue) {
        $users = Get-LocalUser -ErrorAction Stop
        foreach ($u in $users) {
            $lastLog = if ($u.LastLogon) { $u.LastLogon.ToString("yyyy-MM-dd HH:mm") } else { "Never" }
            $pwdLastSet = if ($u.PasswordLastSet) { $u.PasswordLastSet } else { $null }
            $pwdAgeDays = if ($pwdLastSet) { [int]((Get-Date) - $pwdLastSet).TotalDays } else { "N/A" }
            $pwdDoesExpire = ($null -ne $u.PasswordExpires)
            $isLocked = & $getLockoutState $u.Name

            if ($u.Enabled -and $isLocked) {
                $hasLocked = $true
            }

            $results.Add([PSCustomObject]@{
                AccountName     = [string]$u.Name
                Enabled         = [bool]$u.Enabled
                LockedOut       = [bool]$isLocked
                PasswordExpires = $pwdDoesExpire
                PasswordAgeDays = $pwdAgeDays
                LastLogon       = $lastLog
                Description     = if ($u.Description) { [string]$u.Description } else { "No description" }
            })
        }
    }
    else {
        # Fallback using ADSI WinNT provider
        $computer = [ADSI]"WinNT://$env:COMPUTERNAME"
        $users = $computer.Children | Where-Object { $_.SchemaClassName -eq 'User' }
        foreach ($u in $users) {
            $flags = [int]$u.UserFlags.Value
            $isDisabled = ($flags -band 2) -ne 0
            $isLocked = ($flags -band 16) -ne 0
            $pwdNeverExpires = ($flags -band 65536) -ne 0

            if (-not $isDisabled -and $isLocked) {
                $hasLocked = $true
            }

            $lastLoginStr = "Never"
            try {
                if ($u.LastLogin -and $u.LastLogin.Value) {
                    $lastLoginStr = ([datetime]$u.LastLogin.Value).ToString("yyyy-MM-dd HH:mm")
                }
            }
            catch {
                $lastLoginStr = "Never"
            }

            $results.Add([PSCustomObject]@{
                AccountName     = [string]$u.Name
                Enabled         = (-not $isDisabled)
                LockedOut       = $isLocked
                PasswordExpires = (-not $pwdNeverExpires)
                PasswordAgeDays = "N/A"
                LastLogon       = $lastLoginStr
                Description     = if ($u.Description) { [string]$u.Description } else { "No description" }
            })
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No local user accounts enumerated."
    }

    $status = if ($hasLocked) { "warning" } else { "pass" }
    $summary = if ($hasLocked) {
        "Audited $($results.Count) local account(s). Warning: One or more active accounts are currently LOCKED OUT."
    } else {
        "Audited $($results.Count) local account(s). All active accounts are in good standing."
    }
}
catch {
    $status = "error"
    $summary = "Failed to audit local accounts: $($_.Exception.Message)"
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
