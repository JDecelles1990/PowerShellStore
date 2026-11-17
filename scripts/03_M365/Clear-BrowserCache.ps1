<#
.SYNOPSIS
    Purges temporary Internet cache, GPU cache, and code cache for Edge and Google Chrome while preserving passwords and bookmarks.
.PSSTORE_META
    {
        "title": "Clear Browser Cache (Edge & Chrome)",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "TargetBrowser", "type": "string", "default": "All"},
            {"name": "CloseRunningBrowsers", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetBrowser = "All",

    [Parameter(Mandatory = $false)]
    [bool]$CloseRunningBrowsers = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Validate TargetBrowser
    if ($TargetBrowser -notmatch '^(All|Edge|Chrome)$') {
        $TargetBrowser = "All"
    }

    $totalFreedMb = 0.0

    # Browser definitions: process names and relative cache folder paths
    $browserDefs = @()
    if ($TargetBrowser -in @("All", "Edge")) {
        $browserDefs += @{
            Name       = "Microsoft Edge"
            ProcName   = "msedge"
            CacheRoots = @(
                "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache",
                "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Code Cache",
                "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\GPUCache"
            )
        }
    }
    if ($TargetBrowser -in @("All", "Chrome")) {
        $browserDefs += @{
            Name       = "Google Chrome"
            ProcName   = "chrome"
            CacheRoots = @(
                "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache",
                "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Code Cache",
                "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\GPUCache"
            )
        }
    }

    foreach ($b in $browserDefs) {
        # Optionally terminate running instance to release file locks
        if ($CloseRunningBrowsers) {
            try {
                Get-Process -Name $b.ProcName -ErrorAction Stop | Stop-Process -Force -ErrorAction Stop
                Start-Sleep -Milliseconds 300
            }
            catch {
                # Browser not running
            }
        }

        foreach ($cPath in $b.CacheRoots) {
            if (Test-Path -Path $cPath -ErrorAction Stop) {
                $files = @()
                try {
                    $files = @(Get-ChildItem -Path $cPath -Recurse -File -ErrorAction Stop)
                }
                catch {
                    $files = @()
                }
                $folderBytes = if ($files.Count -gt 0) { ($files | Measure-Object -Property Length -Sum).Sum } else { 0 }
                $folderMb = if ($folderBytes) { [math]::Round([double]$folderBytes / 1MB, 2) } else { 0.0 }

                try {
                    Remove-Item -Path "$cPath\*" -Recurse -Force -ErrorAction Stop
                    $cacheStatus = "Cleared"
                }
                catch {
                    $cacheStatus = "Partially Cleared (Some Files Locked)"
                    $errors.Add("$($b.Name) ($(Split-Path $cPath -Leaf)): $($_.Exception.Message)")
                }

                $totalFreedMb += $folderMb
                $results.Add([PSCustomObject]@{
                    Browser       = $b.Name
                    CacheLocation = (Split-Path $cPath -Leaf)
                    FreedMB       = $folderMb
                    Status        = $cacheStatus
                })
            }
            else {
                $results.Add([PSCustomObject]@{
                    Browser       = $b.Name
                    CacheLocation = (Split-Path $cPath -Leaf)
                    FreedMB       = 0.0
                    Status        = "Directory Not Found (Clean)"
                })
            }
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }

    $roundedTotal = [math]::Round($totalFreedMb, 2)
    Write-Output "[SUCCESS] Total browser cache purged: $roundedTotal MB"
    $summary = "Successfully purged $roundedTotal MB of temporary cache files across targeted browser(s)."
}
catch {
    $status = "error"
    $summary = "Failed to clear browser cache: $($_.Exception.Message)"
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
