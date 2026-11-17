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

$status = "pass"
$summary = ""
$driverResults = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$rebootRequired = $false

try {
    # 1. Initialize Windows Update Session
    $updateSession = New-Object -ComObject Microsoft.Update.Session
    $searcher = $updateSession.CreateUpdateSearcher()

    # Search for uninstalled driver updates
    $searchCriteria = "IsInstalled=0 and Type='Driver' and IsHidden=0"
    $searchResult = $searcher.Search($searchCriteria)

    $totalRaw = $searchResult.Updates.Count

    # Filter out optional/browse-only drivers if IncludeOptional is false
    $updatesToDownload = New-Object -ComObject Microsoft.Update.UpdateColl
    $skippedOptional = 0
    for ($i = 0; $i -lt $totalRaw; $i++) {
        $update = $searchResult.Updates.Item($i)
        if (-not $IncludeOptional -and $update.BrowseOnly) {
            $skippedOptional++
            continue
        }
        $updatesToDownload.Add($update) | Out-Null
    }

    $driversFound = $updatesToDownload.Count

    if ($driversFound -eq 0) {
        if ($RescanPnPDevices) {
            try { & pnputil.exe /scan-devices 2>$null | Out-Null } catch {}
        }

        $status = "pass"
        $summary = if ($skippedOptional -gt 0) {
            "No mandatory device driver updates pending ($skippedOptional optional driver(s) skipped). PnP rescanned: $RescanPnPDevices."
        } else {
            "No pending device driver updates found via Windows Update. All drivers are up to date."
        }

        $driverResults.Add([PSCustomObject]@{
            DriverTitle    = "None pending"
            Status         = "Up to date ($skippedOptional optional skipped)"
            ResultCode     = 0
            RebootRequired = $false
        })
    }
    else {
        # 2. Download Driver Updates
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
                    3 { $installedCount++; "Installed (With Warnings)" }
                    4 { "Failed" }
                    5 { "Aborted" }
                    default { "Result $($stepResult.ResultCode)" }
                }

                $driverResults.Add([PSCustomObject]@{
                    DriverTitle    = [string]$up.Title
                    Status         = $statusText
                    ResultCode     = [int]$stepResult.ResultCode
                    RebootRequired = $rebootRequired
                })
            }
        }

        # 4. Rescan PnP Hardware
        if ($RescanPnPDevices) {
            try { & pnputil.exe /scan-devices 2>$null | Out-Null } catch {}
        }

        # 5. Schedule delayed Reboot if configured so JSON output finishes first
        if ($rebootRequired -and $RebootIfRequired) {
            Write-Output "[NOTICE] Reboot is required and RebootIfRequired is enabled. Scheduling restart in 60 seconds..."
            & shutdown.exe /r /t 60 /c "PowerShellStore: Restarting system to complete device driver installation."
        }

        $status = if ($installedCount -gt 0) { "pass" } else { "warning" }
        $summary = "Driver update complete: $installedCount of $driversFound driver(s) installed. Reboot required: $rebootRequired."
    }

    # Human-readable table before JSON envelope
    if ($driverResults.Count -gt 0) {
        $tableOutput = $driverResults | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Failed to update device drivers: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status          = $status
        summary         = $summary
        reboot_required = $rebootRequired
        data            = @($driverResults)
        errors          = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
