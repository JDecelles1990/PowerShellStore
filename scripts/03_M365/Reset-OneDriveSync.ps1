<#
.SYNOPSIS
    Clears stuck sync locks and resets Microsoft OneDrive to resolve 'Processing changes' hangs and sync icon errors.
.PSSTORE_META
    {
        "title": "Reset Microsoft OneDrive Sync",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 45,
        "output_mode": "json",
        "params": [
            {"name": "KillRunningProcess", "type": "bool", "default": true},
            {"name": "RunResetCommand", "type": "bool", "default": true},
            {"name": "RelaunchOneDrive", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$KillRunningProcess = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RunResetCommand = $true,

    [Parameter(Mandatory = $false)]
    [bool]$RelaunchOneDrive = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$actionRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # 1. Terminate Running OneDrive Process
    $processStopped = $false
    if ($KillRunningProcess) {
        $procs = Get-Process -Name "OneDrive", "FileCoAuth" -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($p in $procs) {
                try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
            $processStopped = $true
            $actionRecords.Add([PSCustomObject]@{
                Action  = "Terminate Process"
                Status  = "Success"
                Details = "Stopped running OneDrive and FileCoAuth processes."
            })
            Start-Sleep -Seconds 1
        } else {
            $actionRecords.Add([PSCustomObject]@{
                Action  = "Terminate Process"
                Status  = "Skipped"
                Details = "OneDrive was not actively running."
            })
        }
    }

    # 2. Locate OneDrive Binary
    $oneDriveExe = ""
    $candidates = @(
        (Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\OneDrive\OneDrive.exe"),
        (Join-Path -Path $env:ProgramFiles -ChildPath "Microsoft OneDrive\OneDrive.exe"),
        (Join-Path -Path ${env:ProgramFiles(x86)} -ChildPath "Microsoft OneDrive\OneDrive.exe")
    )

    foreach ($cand in $candidates) {
        if ([System.IO.File]::Exists($cand)) {
            $oneDriveExe = $cand
            break
        }
    }

    if (-not $oneDriveExe) {
        $status = "warning"
        $summary = "Microsoft OneDrive executable was not discovered on this system."
        $actionRecords.Add([PSCustomObject]@{
            Action  = "Locate OneDrive"
            Status  = "Warning"
            Details = "OneDrive executable not found in standard user or system paths."
        })
    }
    else {
        $actionRecords.Add([PSCustomObject]@{
            Action  = "Locate OneDrive"
            Status  = "Success"
            Details = "Found OneDrive at $oneDriveExe"
        })

        # 3. Clean temporary sync cache / stuck lock files
        $settingsPath = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\OneDrive\settings"
        $purgedLocks = 0
        if ([System.IO.Directory]::Exists($settingsPath)) {
            try {
                $lockFiles = [System.IO.Directory]::GetFiles($settingsPath, "*.lock", [System.IO.SearchOption]::AllDirectories)
                foreach ($lf in $lockFiles) {
                    try {
                        [System.IO.File]::Delete($lf)
                        $purgedLocks++
                    } catch {}
                }
            } catch {}
        }
        $actionRecords.Add([PSCustomObject]@{
            Action  = "Clear Sync Locks"
            Status  = "Success"
            Details = "Purged $purgedLocks stale sync lock files."
        })

        # 4. Execute OneDrive Reset Switch
        if ($RunResetCommand) {
            try {
                Start-Process -FilePath $oneDriveExe -ArgumentList "/reset" -ErrorAction Stop
                $actionRecords.Add([PSCustomObject]@{
                    Action  = "Execute Reset"
                    Status  = "Success"
                    Details = "Triggered '$oneDriveExe /reset' command."
                })
                Start-Sleep -Seconds 3
            }
            catch {
                $errors.Add("Failed to execute /reset: $($_.Exception.Message)")
                $actionRecords.Add([PSCustomObject]@{
                    Action  = "Execute Reset"
                    Status  = "Failed"
                    Details = $_.Exception.Message
                })
            }
        }

        # 5. Optional Client Relaunch
        if ($RelaunchOneDrive) {
            try {
                Start-Process -FilePath $oneDriveExe -ErrorAction SilentlyContinue
                $actionRecords.Add([PSCustomObject]@{
                    Action  = "Relaunch Client"
                    Status  = "Success"
                    Details = "Triggered OneDrive background restart."
                })
            }
            catch {
                $actionRecords.Add([PSCustomObject]@{
                    Action  = "Relaunch Client"
                    Status  = "Warning"
                    Details = "Could not restart OneDrive: $($_.Exception.Message)"
                })
            }
        }

        $summary = "OneDrive reset sequence completed successfully."
    }

    # Human-Readable ASCII Table Output
    if ($actionRecords.Count -gt 0) {
        $tableOutput = $actionRecords | Format-Table -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "OneDrive reset failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($actionRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
