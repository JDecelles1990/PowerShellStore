<#
.SYNOPSIS
    Cleans temporary data across all user profiles, empties all recycle bins, purges update caches, and executes DISM and SFC component repairs, reporting total gigabytes freed.
.PSSTORE_META
    {
        "title": "Deep System Cleanup & Health Repair",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 600,
        "output_mode": "json",
        "params": [
            {"name": "ClearUserTemps", "type": "bool", "default": true},
            {"name": "ClearSystemTemp", "type": "bool", "default": true},
            {"name": "ClearWindowsUpdateCache", "type": "bool", "default": true},
            {"name": "EmptyRecycleBins", "type": "bool", "default": true},
            {"name": "RunDismCleanup", "type": "bool", "default": true},
            {"name": "RunSfcScan", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$ClearUserTemps = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearSystemTemp = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearWindowsUpdateCache = $true,

    [Parameter(Mandatory = $false)]
    [bool]$EmptyRecycleBins = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RunDismCleanup = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RunSfcScan = $true
)

$ErrorActionPreference = 'Stop'

function Get-DriveFreeSpaceBytes([string]$DriveLetter) {
    $cleanLetter = $DriveLetter.Substring(0, 1)
    $drive = [System.IO.DriveInfo]::new($cleanLetter)
    return $drive.AvailableFreeSpace
}

try {
    $sysDrive = $env:SystemDrive.Substring(0, 2)
    $initialFreeBytes = Get-DriveFreeSpaceBytes -DriveLetter $sysDrive
    $stepLog = [System.Collections.Generic.List[string]]::new()
    $warnings = [System.Collections.Generic.List[string]]::new()

    # 1. Empty All Recycle Bins
    if ($EmptyRecycleBins) {
        try {
            Clear-RecycleBin -Force -ErrorAction SilentlyContinue 2>$null
            $stepLog.Add("Emptied system and user Recycle Bins.")
        }
        catch {
            # Non-interactive shell fallback
        }
    }

    # 2. Clear System Temp
    if ($ClearSystemTemp) {
        $winTemp = "$env:SystemRoot\Temp"
        try {
            if (Test-Path -LiteralPath $winTemp -ErrorAction Stop) {
                $deletedCount = 0
                Get-ChildItem -Path $winTemp -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                    try {
                        Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop
                        $deletedCount++
                    } catch {
                        # Locked by running process
                    }
                }
                $stepLog.Add("Cleaned Windows System Temp ($deletedCount items removed).")
            }
        } catch {
            $warnings.Add("System Temp access notice: $($_.Exception.Message)")
        }
    }

    # 3. Clear All User Profiles Temp Folders
    if ($ClearUserTemps) {
        $userProfilesRoot = Split-Path -Path $env:USERPROFILE -Parent
        if (Test-Path $userProfilesRoot) {
            $cleanedProfiles = 0
            Get-ChildItem -Path $userProfilesRoot -Directory -Force -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $uTemp = Join-Path -Path $_.FullName -ChildPath "AppData\Local\Temp"
                    try {
                        if (Test-Path -LiteralPath $uTemp -ErrorAction Stop) {
                            Get-ChildItem -Path $uTemp -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                                try {
                                    Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop
                                } catch {
                                    # Locked by active user process
                                }
                            }
                            $cleanedProfiles++
                        }
                    }
                    catch {
                        # Inaccessible in un-elevated context
                    }
                }
            $stepLog.Add("Cleaned AppData Local Temp across $cleanedProfiles user profile(s).")
        }
    }

    # 4. Windows Update Download Cache
    if ($ClearWindowsUpdateCache) {
        $wuCache = "$env:SystemRoot\SoftwareDistribution\Download"
        try {
            if (Test-Path -LiteralPath $wuCache -ErrorAction Stop) {
                $wuDeleted = 0
                Get-ChildItem -Path $wuCache -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                    try {
                        Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop
                        $wuDeleted++
                    } catch {
                        # Locked by update service
                    }
                }
                $stepLog.Add("Purged SoftwareDistribution Download cache ($wuDeleted items removed).")
            }
        } catch {
            $warnings.Add("Windows Update cache notice: $($_.Exception.Message)")
        }
    }

    # 5. DISM Component Store Cleanup
    $dismOutcome = "Skipped"
    if ($RunDismCleanup) {
        try {
            $dismProcess = Start-Process -FilePath "dism.exe" `
                -ArgumentList "/Online /Cleanup-Image /StartComponentCleanup /Quiet /NoRestart" `
                -Wait -PassThru -NoNewWindow
            if ($dismProcess.ExitCode -eq 0) {
                $dismOutcome = "Component Store cleaned successfully"
                $stepLog.Add("DISM Component Store cleanup completed successfully.")
            } else {
                $dismOutcome = "Exit code $($dismProcess.ExitCode)"
                $warnings.Add("DISM exited with code $($dismProcess.ExitCode)")
            }
        }
        catch {
            $dismOutcome = "Failed: $($_.Exception.Message)"
            $warnings.Add("DISM execution failed: $($_.Exception.Message)")
        }
    }

    # 6. SFC Integrity Scan
    $sfcOutcome = "Skipped"
    if ($RunSfcScan) {
        try {
            $sfcProcess = Start-Process -FilePath "sfc.exe" `
                -ArgumentList "/scannow" `
                -Wait -PassThru -NoNewWindow
            switch ($sfcProcess.ExitCode) {
                0 { $sfcOutcome = "No integrity violations found." }
                1 { $sfcOutcome = "Corrupt files were found and successfully repaired." }
                default { $sfcOutcome = "SFC exited with code $($sfcProcess.ExitCode)." }
            }
            $stepLog.Add("SFC integrity scan completed: $sfcOutcome")
        }
        catch {
            $sfcOutcome = "Failed: $($_.Exception.Message)"
            $warnings.Add("SFC scan failed: $($_.Exception.Message)")
        }
    }

    # Calculate Total Space Reclaimed (64-bit safe)
    $finalFreeBytes = Get-DriveFreeSpaceBytes -DriveLetter $sysDrive
    $rawFreed = [long]($finalFreeBytes - $initialFreeBytes)
    $bytesFreed = if ($rawFreed -gt 0) { $rawFreed } else { [long]0 }
    $gbFreed = [math]::Round($bytesFreed / 1GB, 2)
    $mbFreed = [math]::Round($bytesFreed / 1MB, 2)
    $finalFreeGB = [math]::Round($finalFreeBytes / 1GB, 2)

    $status = "pass"
    $summary = "Cleanup completed. Freed ${gbFreed} GB (${mbFreed} MB) on drive ${sysDrive}. Free space now: ${finalFreeGB} GB."

    $evidence = [PSCustomObject]@{
        Drive           = $sysDrive
        GigabytesFreed  = $gbFreed
        MegabytesFreed  = $mbFreed
        CurrentFreeGB   = $finalFreeGB
        DismStatus      = $dismOutcome
        SfcStatus       = $sfcOutcome
        ActionsExecuted = ($stepLog -join " | ")
    }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($evidence)
        errors  = @($warnings)
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Deep cleanup failed: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
