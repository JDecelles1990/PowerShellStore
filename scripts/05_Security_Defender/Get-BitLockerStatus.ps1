<#
.SYNOPSIS
    Queries BitLocker encryption status, protection state, and key protector types on all or specified drives.
.PSSTORE_META
    {
        "title": "Get BitLocker Encryption Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "MountPoint", "type": "string", "default": ""}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$MountPoint = ""
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = "All examined volumes are fully encrypted and protected."
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $volumes = @()

    # Attempt primary method: Get-BitLockerVolume cmdlet
    $hasBitLockerCmdlet = Get-Command -Name Get-BitLockerVolume -ErrorAction SilentlyContinue
    if ($hasBitLockerCmdlet) {
        if (-not [string]::IsNullOrWhiteSpace($MountPoint)) {
            $volumes = @(Get-BitLockerVolume -MountPoint $MountPoint -ErrorAction Stop)
        } else {
            $volumes = @(Get-BitLockerVolume -ErrorAction Stop)
        }

        foreach ($vol in $volumes) {
            $protectors = if ($vol.KeyProtector) {
                ($vol.KeyProtector | ForEach-Object { $_.KeyProtectorType }) -join ", "
            } else {
                "None"
            }

            $isProtected = ($vol.ProtectionStatus -eq "On" -or $vol.ProtectionStatus -eq 1)
            $pctEncrypted = [math]::Round([double]$vol.EncryptionPercentage, 1)

            if (-not $isProtected -or $pctEncrypted -lt 100) {
                $status = "warning"
            }

            $results.Add([PSCustomObject]@{
                MountPoint          = $vol.MountPoint
                VolumeType          = $vol.VolumeType.ToString()
                ProtectionStatus    = if ($isProtected) { "Protected" } else { "Unprotected" }
                EncryptionPercentage= "$pctEncrypted%"
                VolumeStatus        = $vol.VolumeStatus.ToString()
                KeyProtectors       = $protectors
            })
        }
    } else {
        # Fallback method: manage-bde.exe -status
        $manageBde = Join-Path -Path $env:SystemRoot -ChildPath "System32\manage-bde.exe"
        if (Test-Path -Path $manageBde) {
            $targetArg = if (-not [string]::IsNullOrWhiteSpace($MountPoint)) { $MountPoint } else { "-status" }
            $bdeOutput = & $manageBde -status $targetArg 2>&1
            $rawText = ($bdeOutput | Out-String)

            # Parse volume blocks from manage-bde output
            $volumeBlocks = $rawText -split "Volume ([A-Za-z]:)"
            for ($i = 1; $i -lt $volumeBlocks.Count; $i += 2) {
                $driveLetter = $volumeBlocks[$i]
                $blockData = $volumeBlocks[$i + 1]

                $convStatus = if ($blockData -match "Conversion Status:\s*(.+)") { $Matches[1].Trim() } else { "Unknown" }
                $pct = if ($blockData -match "Percentage Encrypted:\s*(.+)") { $Matches[1].Trim() } else { "Unknown" }
                $protStatus = if ($blockData -match "Protection Status:\s*(.+)") { $Matches[1].Trim() } else { "Unknown" }

                $isProt = ($protStatus -match "Protection On")
                if (-not $isProt -or $pct -notmatch "100") {
                    $status = "warning"
                }

                $results.Add([PSCustomObject]@{
                    MountPoint           = $driveLetter
                    VolumeType           = "FixedDisk"
                    ProtectionStatus     = if ($isProt) { "Protected" } else { "Unprotected" }
                    EncryptionPercentage = $pct
                    VolumeStatus         = $convStatus
                    KeyProtectors        = "manage-bde queried"
                })
            }
        } else {
            throw "Neither Get-BitLockerVolume nor manage-bde.exe is available on this system."
        }
    }

    if ($results.Count -eq 0) {
        $status = "warning"
        $summary = "No BitLocker-compatible volumes were discovered."
    } elseif ($status -eq "warning") {
        $unprot = ($results | Where-Object { $_.ProtectionStatus -ne "Protected" -or $_.EncryptionPercentage -notmatch "100" }).Count
        $summary = "Warning: $unprot volume(s) are unencrypted or unprotected."
    } else {
        $summary = "$($results.Count) volume(s) verified fully encrypted and protected."
    }
}
catch {
    $status = "error"
    $summary = "Failed to query BitLocker status: $($_.Exception.Message)"
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

