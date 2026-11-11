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

try {
    # Validate TargetBrowser
    if ($TargetBrowser -notmatch '^(All|Edge|Chrome)$') {
        $TargetBrowser = "All"
    }

    $results = @()
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
            Get-Process -Name $b.ProcName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 300
        }

        foreach ($cPath in $b.CacheRoots) {
            if (Test-Path $cPath) {
                # Calculate size before deletion
                $files = Get-ChildItem -Path $cPath -Recurse -File -ErrorAction SilentlyContinue
                $folderBytes = ($files | Measure-Object -Property Length -Sum).Sum
                $folderMb = if ($folderBytes) { [math]::Round($folderBytes / 1MB, 2) } else { 0.0 }

                # Remove cache files safely
                Remove-Item -Path "$cPath\*" -Recurse -Force -ErrorAction SilentlyContinue

                $totalFreedMb += $folderMb
                $results += [PSCustomObject]@{
                    Browser       = $b.Name
                    CacheLocation = (Split-Path $cPath -Leaf)
                    FreedMB       = $folderMb
                    Status        = "Cleared"
                }
            }
            else {
                $results += [PSCustomObject]@{
                    Browser       = $b.Name
                    CacheLocation = (Split-Path $cPath -Leaf)
                    FreedMB       = 0.0
                    Status        = "Directory Not Found (Clean)"
                }
            }
        }
    }

    # Human-readable table first
    $results | Format-Table -AutoSize | Out-String | Write-Output

    $roundedTotal = [math]::Round($totalFreedMb, 2)
    Write-Output "[SUCCESS] Total browser cache purged: $roundedTotal MB"

    $payload = @{
        status  = "pass"
        summary = "Successfully purged $roundedTotal MB of temporary cache files across targeted browser(s)."
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to clear browser cache: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
