<#
.SYNOPSIS
    Clears cache files for both Classic and New Microsoft Teams clients and terminates background processes to resolve meeting crashes and sign-in loops.
.PSSTORE_META
    {
        "title": "Clear Microsoft Teams Cache",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "KillRunningProcesses", "type": "bool", "default": true},
            {"name": "RelaunchTeams", "type": "bool", "default": false}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$KillRunningProcesses = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RelaunchTeams = $false
)

$ErrorActionPreference = 'Stop'

try {
    $actions = [System.Collections.Generic.List[string]]::new()
    $warnings = [System.Collections.Generic.List[string]]::new()

    # 1. Terminate running Teams processes
    if ($KillRunningProcesses) {
        $processes = Get-Process -Name "Teams", "ms-teams" -ErrorAction SilentlyContinue
        if ($processes) {
            foreach ($p in $processes) {
                try {
                    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                } catch {}
            }
            $actions.Add("Terminated running Teams processes.")
            Start-Sleep -Seconds 1
        }
    }

    # 2. Clear Classic Teams Cache (%appdata%\Microsoft\Teams)
    $classicPath = "$env:APPDATA\Microsoft\Teams"
    $classicCleared = $false
    if (Test-Path $classicPath) {
        $subfolders = @(
            "blob_storage", "databases", "GPUCache", "IndexedDB",
            "Local Storage", "tmp", "Cache", "code cache"
        )
        foreach ($sub in $subfolders) {
            $target = Join-Path -Path $classicPath -ChildPath $sub
            if (Test-Path $target) {
                try {
                    Remove-Item -Path "$target\*" -Recurse -Force -ErrorAction SilentlyContinue
                } catch {}
            }
        }
        $classicCleared = $true
        $actions.Add("Purged Classic Teams cache directories.")
    }

    # 3. Clear New Teams v2 Cache (%localappdata%\Packages\MSTeams_8wekyb3d8bbwe)
    $newTeamsRoot = "$env:LOCALAPPDATA\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams"
    $newCleared = $false
    if (Test-Path $newTeamsRoot) {
        try {
            Remove-Item -Path "$newTeamsRoot\*" -Recurse -Force -ErrorAction SilentlyContinue
            $newCleared = $true
            $actions.Add("Purged New Teams (v2) LocalCache files.")
        }
        catch {
            $warnings.Add("Notice clearing New Teams cache: $($_.Exception.Message)")
        }
    }

    # 4. Optional Relaunch
    if ($RelaunchTeams) {
        try {
            Start-Process "ms-teams:" -ErrorAction SilentlyContinue
            $actions.Add("Triggered New Teams client launch.")
        } catch {
            $warnings.Add("Failed to relaunch Teams: $($_.Exception.Message)")
        }
    }

    $summary = "Teams cache cleanup completed. Classic cleared: $classicCleared | New Teams cleared: $newCleared."
    $evidence = [PSCustomObject]@{
        ClassicTeamsCacheCleared = $classicCleared
        NewTeamsCacheCleared     = $newCleared
        ProcessesTerminated      = $KillRunningProcesses
        Relaunched               = $RelaunchTeams
        ActionsLog               = ($actions -join " | ")
    }

    $payload = @{
        status  = "pass"
        summary = $summary
        data    = @($evidence)
        errors  = @($warnings)
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Failed to clear Teams cache: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
