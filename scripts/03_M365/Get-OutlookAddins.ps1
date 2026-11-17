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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Search registry locations for Outlook add-ins
    $registryKeys = @(
        @{ Path = "HKCU:\SOFTWARE\Microsoft\Office\Outlook\Addins"; Scope = "Current User" },
        @{ Path = "HKLM:\SOFTWARE\Microsoft\Office\Outlook\Addins"; Scope = "Machine (64-bit)" },
        @{ Path = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\Outlook\Addins"; Scope = "Machine (32-bit)" }
    )

    foreach ($reg in $registryKeys) {
        try {
            if (Test-Path -Path $reg.Path -ErrorAction Stop) {
                $subKeys = Get-ChildItem -Path $reg.Path -ErrorAction Stop
                foreach ($sk in $subKeys) {
                    $props = Get-ItemProperty -Path $sk.PSPath -ErrorAction SilentlyContinue
                    $progId = Split-Path -Path $sk.Name -Leaf
                    $friendlyName = if ($props -and $props.FriendlyName) { [string]$props.FriendlyName } else { $progId }
                    $loadVal = if ($props -and $null -ne $props.LoadBehavior) { [int]$props.LoadBehavior } else { -1 }

                    $statusText = switch ($loadVal) {
                        3 { "Active (Loaded at Startup)" }
                        2 { "Disabled (Do Not Load)" }
                        1 { "Load on Demand" }
                        0 { "Inactive" }
                        default { "Unknown ($loadVal)" }
                    }

                    $results.Add([PSCustomObject]@{
                        AddinName         = $friendlyName
                        ProgId            = $progId
                        LoadBehavior      = $loadVal
                        StatusDescription = $statusText
                        Scope             = $reg.Scope
                        Details           = if ($props -and $props.Description) { [string]$props.Description } else { "No description" }
                    })
                }
            }
        }
        catch {
            $errors.Add("Registry access notice ($($reg.Scope)): $($_.Exception.Message)")
        }
    }

    # Optional .OST File Size Audit
    if ($CheckOSTSize -and $env:LOCALAPPDATA) {
        try {
            $ostDir = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\Outlook"
            if (Test-Path -Path $ostDir -ErrorAction Stop) {
                $ostFiles = Get-ChildItem -Path $ostDir -Filter "*.ost" -File -ErrorAction Stop
                foreach ($ost in $ostFiles) {
                    $sizeGb = [math]::Round($ost.Length / 1GB, 2)
                    $health = if ($sizeGb -gt 40) { "Warning: Approaching 50GB Limit" } else { "Normal ($sizeGb GB)" }

                    $results.Add([PSCustomObject]@{
                        AddinName         = "[OST Cache File]"
                        ProgId            = $ost.Name
                        LoadBehavior      = 0
                        StatusDescription = $health
                        Scope             = "Local Mailbox Cache"
                        Details           = "Full Path: $($ost.FullName)"
                    })
                }
            }
        }
        catch {
            $errors.Add("OST audit notice: $($_.Exception.Message)")
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No Outlook COM Add-ins or .OST files detected."
    }

    if ($errors.Count -gt 0 -and $results.Count -eq 0) {
        $status = "warning"
        $summary = "Outlook audit finished with access notices ($($errors.Count))."
    }
    else {
        $summary = "Discovered $($results.Count) Outlook Add-in and mailbox cache artifact(s)."
    }
}
catch {
    $status = "error"
    $summary = "Failed to query Outlook Add-ins: $($_.Exception.Message)"
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
