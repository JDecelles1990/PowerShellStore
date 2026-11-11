<#
.SYNOPSIS
    Scans for and installs all pending device driver updates via the Windows Update Agent and triggers PnP hardware matching.
.PSSTORE_META
    {
        "title": "Update All Device Drivers",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 600,
        "output_mode": "json",
        "params": [
            {"name": "IncludeOptional", "type": "bool", "default": true},
            {"name": "RescanPnPDevices", "type": "bool", "default": true},
            {"name": "RebootIfRequired", "type": "bool", "default": false}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeOptional = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RescanPnPDevices = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RebootIfRequired = $false
)

$ErrorActionPreference = 'Stop'

try {
    $driverResults = [System.Collections.Generic.List[PSObject]]::new()
    $rebootRequired = $false

    # 1. Initialize Windows Update Session
    $updateSession = New-Object -ComObject Microsoft.Update.Session
    $searcher = $updateSession.CreateUpdateSearcher()

    # Search for uninstalled driver updates
    $searchCriteria = "IsInstalled=0 and Type='Driver' and IsHidden=0"
    $searchResult = $searcher.Search($searchCriteria)

    $driversFound = $searchResult.Updates.Count

    if ($driversFound -eq 0) {
        # Rescan PnP devices if requested
        if ($RescanPnPDevices) {
            try { & pnputil.exe /scan-devices 2>$null } catch {}
        }

        $summary = "No pending device driver updates found via Windows Update. All drivers are up to date."
        $payload = @{
            status  = "pass"
            summary = $summary
            data    = @([PSCustomObject]@{
                DriversFound      = 0
                DriversInstalled  = 0
                RebootRequired    = $false
                PnPRescanned      = $RescanPnPDevices
            })
            errors  = @()
        }
    }
    else {
        # 2. Download Driver Updates
        $updatesToDownload = New-Object -ComObject Microsoft.Update.UpdateColl
        for ($i = 0; $i -lt $searchResult.Updates.Count; $i++) {
            $update = $searchResult.Updates.Item($i)
            $updatesToDownload.Add($update) | Out-Null
        }

        $downloader = $updateSession.CreateUpdateDownloader()
        $downloader.Updates = $updatesToDownload
        $downloadResult = $downloader.Download()

        # 3. Install Downloaded Driver Updates
        $updatesToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
        for ($i = 0; $i -lt $updatesToDownload.Count; $i++) {
            $up = $updatesToDownload.Item($i)
            if ($up.IsDownloaded) {
                $updatesToInstall.Add($up) | Out-Null
            }
        }

        $installedCount = 0
        if ($updatesToInstall.Count -gt 0) {
            $installer = $updateSession.CreateUpdateInstaller()
            $installer.Updates = $updatesToInstall
            $installResult = $installer.Install()

            $rebootRequired = [bool]$installResult.RebootRequired

            for ($i = 0; $i -lt $updatesToInstall.Count; $i++) {
                $up = $updatesToInstall.Item($i)
                $stepResult = $installResult.GetUpdateResult($i)
                $statusText = switch ($stepResult.ResultCode) {
                    2 { $installedCount++; "Installed" }
                    3 { "Installed (With Warnings)" }
                    4 { "Failed" }
                    5 { "Aborted" }
                    default { "Result $($stepResult.ResultCode)" }
                }

                $driverResults.Add([PSCustomObject]@{
                    DriverTitle = [string]$up.Title
                    Status      = $statusText
                    ResultCode  = [int]$stepResult.ResultCode
                })
            }
        }

        # 4. Rescan PnP Hardware
        if ($RescanPnPDevices) {
            try { & pnputil.exe /scan-devices 2>$null } catch {}
        }

        # 5. Handle Reboot if configured
        if ($rebootRequired -and $RebootIfRequired) {
            Restart-Computer -Force
        }

        $status = if ($installedCount -gt 0) { "pass" } else { "warning" }
        $summary = "Driver update complete: $installedCount of $driversFound driver(s) installed. Reboot required: $rebootRequired."

        $payload = @{
            status  = $status
            summary = $summary
            data    = @($driverResults)
            errors  = @()
        }
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Failed to update device drivers: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}

