<#
.SYNOPSIS
    Enumerates members of the local Administrators group, identifying account types (Local, Domain, Entra ID) for security posture auditing.
.PSSTORE_META
    {
        "title": "Audit Local Administrators",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "IncludeBuiltInAdmin", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeBuiltInAdmin = $true
)

$ErrorActionPreference = 'Stop'

try {
    $membersList = [System.Collections.Generic.List[PSObject]]::new()

    # Query local group members via Get-LocalGroupMember (fallback to ADSI)
    try {
        $groupMembers = Get-LocalGroupMember -Group "Administrators" -ErrorAction Stop
        foreach ($member in $groupMembers) {
            $name = $member.Name
            $objectClass = $member.ObjectClass
            $sid = $member.SID.Value

            # Account source classification
            $accountType = "Local"
            if ($name -match "^AzureAD\\" -or $name -match "^\w+@") {
                $accountType = "Microsoft Entra ID"
            } elseif ($name -match "\\") {
                $domainPart = $name.Split('\')[0]
                if ($domainPart -ne $env:COMPUTERNAME) {
                    $accountType = "Active Directory Domain"
                }
            }

            if (-not $IncludeBuiltInAdmin -and $sid -match "-500$") {
                continue
            }

            $membersList.Add([PSCustomObject]@{
                AccountName = $name
                AccountType = $accountType
                ObjectClass = $objectClass
                SID         = $sid
            })
        }
    }
    catch {
        # ADSI fallback for older environments
        $adminGroup = [ADSI]"WinNT://$env:COMPUTERNAME/Administrators,group"
        $adsiMembers = @($adminGroup.psbase.Invoke("Members"))
        foreach ($m in $adsiMembers) {
            $path = $m.GetType().InvokeMember("AdsPath", "GetProperty", $null, $m, $null)
            $name = $path.Replace("WinNT://", "").Replace("/", "\")
            $membersList.Add([PSCustomObject]@{
                AccountName = $name
                AccountType = "Local/Domain"
                ObjectClass = "User"
                SID         = "N/A"
            })
        }
    }

    $count = $membersList.Count
    $status = if ($count -gt 3) { "warning" } else { "pass" }
    $summary = if ($count -gt 3) {
        "WARNING: Found $count local administrators. Review members to minimize endpoint attack surface."
    } else {
        "Found $count member(s) in the local Administrators group."
    }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($membersList)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Failed to audit local administrators: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}

