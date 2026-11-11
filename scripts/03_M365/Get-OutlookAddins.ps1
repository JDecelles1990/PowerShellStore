<#
.SYNOPSIS
    Audits installed Outlook COM Add-ins, LoadBehavior flags, and local .OST mailbox cache file sizes.
.PSSTORE_META
    {
        "title": "Get Outlook COM Add-ins & Cache Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "CheckOSTSize", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$CheckOSTSize = $true
)

$ErrorActionPreference = 'Stop'

try {
    $results = @()

    # Search registry locations for Outlook add-ins
    $registryKeys = @(
        @{ Path = "HKCU:\SOFTWARE\Microsoft\Office\Outlook\Addins"; Scope = "Current User" },
        @{ Path = "HKLM:\SOFTWARE\Microsoft\Office\Outlook\Addins"; Scope = "Machine (64-bit)" },
        @{ Path = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\Outlook\Addins"; Scope = "Machine (32-bit)" }
    )

    foreach ($reg in $registryKeys) {
        if (Test-Path $reg.Path) {
            $subKeys = Get-ChildItem -Path $reg.Path -ErrorAction SilentlyContinue
            foreach ($sk in $subKeys) {
                $props = Get-ItemProperty -Path $sk.PSPath -ErrorAction SilentlyContinue
                $progId = Split-Path $sk.Name -Leaf
                $friendlyName = if ($props.FriendlyName) { $props.FriendlyName } else { $progId }
                $loadVal = if ($null -ne $props.LoadBehavior) { [int]$props.LoadBehavior } else { -1 }

                $statusText = switch ($loadVal) {
                    3 { "Active (Loaded at Startup)" }
                    2 { "Disabled (Do Not Load)" }
                    1 { "Load on Demand" }
                    0 { "Inactive" }
                    default { "Unknown ($loadVal)" }
                }

                $results += [PSCustomObject]@{
                    AddinName         = $friendlyName
                    ProgId            = $progId
                    LoadBehavior      = $loadVal
                    StatusDescription = $statusText
                    Scope             = $reg.Scope
                    Details           = if ($props.Description) { $props.Description } else { "No description" }
                }
            }
        }
    }

    # Optional .OST File Size Audit
    if ($CheckOSTSize) {
        $ostDir = "$env:LOCALAPPDATA\Microsoft\Outlook"
        if (Test-Path $ostDir) {
            $ostFiles = Get-ChildItem -Path $ostDir -Filter "*.ost" -File -ErrorAction SilentlyContinue
            foreach ($ost in $ostFiles) {
                $sizeGb = [math]::Round($ost.Length / 1GB, 2)
                $health = if ($sizeGb -gt 40) { "Warning: Approaching 50GB Limit" } else { "Normal ($sizeGb GB)" }

                $results += [PSCustomObject]@{
                    AddinName         = "[OST Cache File]"
                    ProgId            = $ost.Name
                    LoadBehavior      = 0
                    StatusDescription = $health
                    Scope             = "Local Mailbox Cache"
                    Details           = "Full Path: $($ost.FullName)"
                }
            }
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $results | Format-Table -AutoSize | Out-String | Write-Output
    }
    else {
        Write-Output "No Outlook COM Add-ins or .OST files detected in the registry."
    }

    $payload = @{
        status  = "pass"
        summary = "Discovered $($results.Count) Outlook Add-in and mailbox cache artifact(s)."
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query Outlook Add-ins: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

