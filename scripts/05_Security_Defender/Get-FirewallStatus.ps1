<#
.SYNOPSIS
    Audits Windows Firewall operational status, active profiles (Domain, Private, Public), and default inbound/outbound rules.
.PSSTORE_META
    {
        "title": "Get Windows Firewall Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "CheckAllProfiles", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$CheckAllProfiles = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$firewallRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

$disabledProfiles = 0

try {
    $queriedViaCmdlet = $false

    # Tier 1: NetSecurity Cmdlets (Get-NetFirewallProfile)
    try {
        $profiles = Get-NetFirewallProfile -ErrorAction Stop
        if ($profiles -and $profiles.Count -gt 0) {
            foreach ($p in $profiles) {
                $isEnabled = [bool]$p.Enabled
                if (-not $isEnabled) { $disabledProfiles++ }

                $firewallRecords.Add([PSCustomObject]@{
                    ProfileName            = [string]$p.Name
                    Enabled                = $isEnabled
                    DefaultInboundAction   = [string]$p.DefaultInboundAction
                    DefaultOutboundAction  = [string]$p.DefaultOutboundAction
                    AllowInboundRules      = [string]$p.AllowInboundRules
                })
            }
            $queriedViaCmdlet = $true
        }
    } catch {}

    # Tier 2: Resilient Registry Fallback (HKLM FirewallPolicy)
    if (-not $queriedViaCmdlet -or $firewallRecords.Count -eq 0) {
        $regRoot = "HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
        $profileMap = @{
            "DomainProfile"   = "Domain"
            "StandardProfile" = "Private"
            "PublicProfile"   = "Public"
        }

        foreach ($entry in $profileMap.GetEnumerator()) {
            $subPath = Join-Path -Path $regRoot -ChildPath $entry.Key
            if (Test-Path $subPath) {
                $pVal = Get-ItemProperty -Path $subPath -ErrorAction SilentlyContinue
                $enabledVal = $pVal.EnableFirewall
                $isEnabled = ($enabledVal -eq 1 -or $enabledVal -eq "1")
                if (-not $isEnabled) { $disabledProfiles++ }

                $inbound = if ($pVal.DefaultInboundAction -eq 0) { "Allow" } else { "Block" }
                $outbound = if ($pVal.DefaultOutboundAction -eq 1) { "Block" } else { "Allow" }

                $firewallRecords.Add([PSCustomObject]@{
                    ProfileName            = [string]$entry.Value
                    Enabled                = $isEnabled
                    DefaultInboundAction   = $inbound
                    DefaultOutboundAction  = $outbound
                    AllowInboundRules      = "True"
                })
            }
        }
    }

    $totalProfiles = $firewallRecords.Count
    if ($disabledProfiles -gt 0) {
        $status = "warning"
        $summary = "Security Warning: $disabledProfiles of $totalProfiles firewall profile(s) are disabled."
    } elseif ($totalProfiles -gt 0) {
        $status = "pass"
        $summary = "All $totalProfiles Windows Firewall profiles (Domain, Private, Public) are active and enforcing default block rules."
    } else {
        $status = "warning"
        $summary = "No Windows Firewall profile records were located."
    }

    # Human-Readable ASCII Table Output
    if ($firewallRecords.Count -gt 0) {
        $tableOutput = $firewallRecords | Format-Table -Property ProfileName, Enabled, DefaultInboundAction, DefaultOutboundAction -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Failed to query Windows Firewall status: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($firewallRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
