<#
.SYNOPSIS
    Scans, downloads, and installs pending Windows software and security updates via the Windows Update Agent.
.PSSTORE_META
    {
        "title": "Install Windows Updates",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 900,
        "output_mode": "json",
        "params": [
            {"name": "ScanOnly", "type": "bool", "default": false},
            {"name": "AutoReboot", "type": "bool", "default": false},
            {"name": "MaxUpdates", "type": "int", "default": 25, "min": 1, "max": 100}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$ScanOnly = $false,

    [Parameter(Mandatory = $false)]
    [bool]$AutoReboot = $false,

    [Parameter(Mandatory = $false)]
    [int]$MaxUpdates = 25
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$updateRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$rebootRequired = $false

try {
    # 1. Initialize Windows Update Session COM Object
    $updateSession = New-Object -ComObject Microsoft.Update.Session
    $searcher = $updateSession.CreateUpdateSearcher()

    # Search for pending, uninstalled software and security updates
    $searchCriteria = "IsInstalled=0 and Type='Software' and IsHidden=0"
    $searchResult = $searcher.Search($searchCriteria)

    $totalFound = $searchResult.Updates.Count

    if ($totalFound -eq 0) {
        $status = "pass"
        $summary = "System is up to date. No pending Windows updates found."
        $updateRecords.Add([PSCustomObject]@{
            Title          = "No pending updates"
            KBArticleID    = "N/A"
            SizeMB         = 0
            Result         = "Up to date"
            RebootRequired = $false
        })
    }
    elseif ($ScanOnly) {
        # 2. Scan Only Mode: Display pending updates without installing
        $status = "warning"
        $summary = "Found $totalFound pending Windows update(s). Scan-only requested."

        $limit = [math]::Min($totalFound, $MaxUpdates)
        for ($i = 0; $i -lt $limit; $i++) {
            $up = $searchResult.Updates.Item($i)
            $kbList = ($up.KBArticleIDs | ForEach-Object { "KB$_" }) -join ", "
            if (-not $kbList) { $kbList = "N/A" }
            $sizeMb = [math]::Round([double]$up.MaxDownloadSize / 1MB, 2)

            $updateRecords.Add([PSCustomObject]@{
                Title          = [string]$up.Title
                KBArticleID    = $kbList
                SizeMB         = $sizeMb
                Result         = "Pending (Not Installed)"
                RebootRequired = [bool]$up.RebootRequired
            })
        }
    }
    else {
        # 3. Download & Install Mode
        $limit = [math]::Min($totalFound, $MaxUpdates)
        $updatesToDownload = New-Object -ComObject Microsoft.Update.UpdateColl

        for ($i = 0; $i -lt $limit; $i++) {
            $up = $searchResult.Updates.Item($i)
            # Accept EULA if required
            if (-not $up.EulaAccepted) {
                try { $up.AcceptEula() } catch {}
            }
            $updatesToDownload.Add($up) | Out-Null
        }

        # Step A: Download
        $downloader = $updateSession.CreateUpdateDownloader()
        $downloader.Updates = $updatesToDownload
        $downloadResult = $downloader.Download()

        # Step B: Filter successfully downloaded updates
        $updatesToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
        for ($i = 0; $i -lt $updatesToDownload.Count; $i++) {
            $up = $updatesToDownload.Item($i)
            if ($up.IsDownloaded) {
                $updatesToInstall.Add($up) | Out-Null
            }
        }

        # Step C: Install
        $installedCount = 0
        $failedCount = 0

        if ($updatesToInstall.Count -gt 0) {
            $installer = $updateSession.CreateUpdateInstaller()
            $installer.Updates = $updatesToInstall
            $installResult = $installer.Install()

            $rebootRequired = [bool]$installResult.RebootRequired

            for ($i = 0; $i -lt $updatesToInstall.Count; $i++) {
                $up = $updatesToInstall.Item($i)
                $stepResult = $installResult.GetUpdateResult($i)
                $kbList = ($up.KBArticleIDs | ForEach-Object { "KB$_" }) -join ", "
                if (-not $kbList) { $kbList = "N/A" }
                $sizeMb = [math]::Round([double]$up.MaxDownloadSize / 1MB, 2)

                $statusText = switch ($stepResult.ResultCode) {
                    2 { $installedCount++; "Installed Successfully" }
                    3 { $installedCount++; "Installed (With Warnings)" }
                    4 { $failedCount++; "Failed" }
                    5 { $failedCount++; "Aborted" }
                    default { "Result Code: $($stepResult.ResultCode)" }
                }

                $updateRecords.Add([PSCustomObject]@{
                    Title          = [string]$up.Title
                    KBArticleID    = $kbList
                    SizeMB         = $sizeMb
                    Result         = $statusText
                    RebootRequired = $rebootRequired
                })
            }
        } else {
            $status = "warning"
            $summary = "Updates were discovered but could not be downloaded."
        }

        if ($installedCount -gt 0) {
            $status = if ($failedCount -eq 0) { "pass" } else { "warning" }
            $summary = "Successfully installed $installedCount update(s)." + $(if ($rebootRequired) { " System reboot is required." } else { "" })
        } elseif ($failedCount -gt 0) {
            $status = "fail"
            $summary = "Failed to install $failedCount update(s)."
        }

        # Optional Automatic Reboot
        if ($AutoReboot -and $rebootRequired) {
            Write-Output "[NOTICE] Reboot is required and AutoReboot is enabled. Initiating system restart in 60 seconds..."
            shutdown.exe /r /t 60 /c "PowerShellStore: Restarting system to complete Windows Update installation."
        }
    }

    # Human-Readable Formatted Table for RMM and Console
    if ($updateRecords.Count -gt 0) {
        $tableOutput = $updateRecords | Format-Table -Property KBArticleID, Result, SizeMB, Title -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Windows Update execution failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status         = $status
        summary        = $summary
        reboot_required= $rebootRequired
        data           = @($updateRecords)
        errors         = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}

