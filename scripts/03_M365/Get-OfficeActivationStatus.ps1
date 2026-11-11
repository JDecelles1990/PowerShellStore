<#
.SYNOPSIS
    Queries Microsoft 365 Apps and Office activation state, installed license edition, build version, and Shared Computer Licensing status.
.PSSTORE_META
    {
        "title": "Get Office & M365 Activation Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "CheckVolumeLicensing", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$CheckVolumeLicensing = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$officeRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # 1. Inspect Modern Click-to-Run Office Registry
    $c2rPath = "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration"
    $hasC2R = Test-Path $c2rPath
    $productReleaseIds = "None"
    $versionToReport = "N/A"
    $platform = "N/A"
    $sharedLicensing = "Disabled"
    $updateChannel = "Standard"

    if ($hasC2R) {
        $c2r = Get-ItemProperty -Path $c2rPath -ErrorAction SilentlyContinue
        if ($c2r.ProductReleaseIds) { $productReleaseIds = [string]$c2r.ProductReleaseIds }
        if ($c2r.VersionToReport) { $versionToReport = [string]$c2r.VersionToReport }
        if ($c2r.Platform) { $platform = [string]$c2r.Platform }
        if ($c2r.SharedComputerLicensing -eq "1" -or $c2r.SharedComputerLicensing -eq 1) {
            $sharedLicensing = "Enabled (Shared Computer / RDS)"
        }
        if ($c2r.UpdateChannel) { $updateChannel = [string]$c2r.UpdateChannel }
    }

    # 2. Check Volume Licensing via OSPP.vbs if present
    $licenseStatus = "Licensed (Click-to-Run Subscription)"
    $partialKey = "N/A"

    if ($CheckVolumeLicensing) {
        $osppCandidates = @(
            (Join-Path -Path $env:ProgramFiles -ChildPath "Microsoft Office\Office16\OSPP.VBS"),
            (Join-Path -Path ${env:ProgramFiles(x86)} -ChildPath "Microsoft Office\Office16\OSPP.VBS"),
            (Join-Path -Path $env:ProgramFiles -ChildPath "Microsoft Office\Office15\OSPP.VBS")
        )

        foreach ($ospp in $osppCandidates) {
            if ([System.IO.File]::Exists($ospp)) {
                try {
                    $cscript = Join-Path -Path $env:SystemRoot -ChildPath "System32\cscript.exe"
                    $osppOutput = & $cscript //nologo $ospp /dstatus 2>&1 | Out-String
                    if ($osppOutput -match "LICENSE STATUS:\s*---(.+)---") {
                        $licenseStatus = $Matches[1].Trim()
                    }
                    if ($osppOutput -match "Last 5 characters of installed product key:\s*(.+)") {
                        $partialKey = $Matches[1].Trim()
                    }
                } catch {}
                break
            }
        }
    }

    # 3. Signed-in Corporate Identity Check
    $signedInAccount = "Unknown / Not signed in"
    try {
        $identPath = "HKCU:\Software\Microsoft\Office\16.0\Common\Identity\Identities"
        if (Test-Path $identPath) {
            $subIdentities = Get-ChildItem -Path $identPath -ErrorAction SilentlyContinue
            if ($subIdentities) {
                foreach ($idKey in $subIdentities) {
                    $email = $idKey.GetValue("EmailAddress")
                    if ($email) {
                        $signedInAccount = [string]$email
                        break
                    }
                }
            }
        }
    } catch {}

    if (-not $hasC2R -and $productReleaseIds -eq "None") {
        $status = "warning"
        $summary = "No Microsoft Office or Microsoft 365 Apps installation discovered."
    } else {
        $summary = "Office: $productReleaseIds ($versionToReport, $platform) | Status: $licenseStatus | Shared Licensing: $sharedLicensing"
    }

    $officeRecords.Add([PSCustomObject]@{
        ProductReleases          = $productReleaseIds
        Version                  = $versionToReport
        Architecture             = $platform
        LicenseStatus            = $licenseStatus
        SharedComputerLicensing  = $sharedLicensing
        PartialProductKey        = $partialKey
        SignedInAccount          = $signedInAccount
    })

    # Human-Readable ASCII Table Output
    $displayRows = @(
        [PSCustomObject]@{ Attribute = "Installed Products"; Value = $productReleaseIds },
        [PSCustomObject]@{ Attribute = "Reported Version"; Value = $versionToReport },
        [PSCustomObject]@{ Attribute = "Architecture"; Value = $platform },
        [PSCustomObject]@{ Attribute = "License Status"; Value = $licenseStatus },
        [PSCustomObject]@{ Attribute = "Shared Computer Licensing"; Value = $sharedLicensing },
        [PSCustomObject]@{ Attribute = "Partial Product Key"; Value = $partialKey },
        [PSCustomObject]@{ Attribute = "Signed In Account"; Value = $signedInAccount }
    )
    $tableOutput = $displayRows | Format-Table -AutoSize | Out-String
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Failed to query Office activation status: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($officeRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}

