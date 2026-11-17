<#
.SYNOPSIS
    Audits applications and scheduled tasks configured to launch automatically at Windows boot or user logon.
.PSSTORE_META
    {
        "title": "Get Startup Applications & Tasks",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 25,
        "output_mode": "json",
        "params": [
            {"name": "IncludeScheduledTasks", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeScheduledTasks = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # 1. Inspect HKCU Run key
    try {
        $hkcuRunPath = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        if (Test-Path -Path $hkcuRunPath -ErrorAction Stop) {
            $hkcuProps = Get-ItemProperty -Path $hkcuRunPath -ErrorAction Stop
            if ($hkcuProps) {
                foreach ($propName in $hkcuProps.PSObject.Properties.Name) {
                    if ($propName -notmatch '^PS.*') {
                        $results.Add([PSCustomObject]@{
                            Name      = $propName
                            Source    = "Registry HKCU:Run"
                            Command   = [string]$hkcuProps.$propName
                            UserScope = $env:USERNAME
                            Status    = "Active"
                        })
                    }
                }
            }
        }
    }
    catch {
        $errors.Add("HKCU Run key notice: $($_.Exception.Message)")
    }

    # 2. Inspect HKLM Run key (System-wide)
    try {
        $hklmRunPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        if (Test-Path -Path $hklmRunPath -ErrorAction Stop) {
            $hklmProps = Get-ItemProperty -Path $hklmRunPath -ErrorAction Stop
            if ($hklmProps) {
                foreach ($propName in $hklmProps.PSObject.Properties.Name) {
                    if ($propName -notmatch '^PS.*') {
                        $results.Add([PSCustomObject]@{
                            Name      = $propName
                            Source    = "Registry HKLM:Run"
                            Command   = [string]$hklmProps.$propName
                            UserScope = "All Users"
                            Status    = "Active"
                        })
                    }
                }
            }
        }
    }
    catch {
        $errors.Add("HKLM Run key notice: $($_.Exception.Message)")
    }

    # 3. Inspect User Startup Folder
    try {
        $userStartup = [Environment]::GetFolderPath('Startup')
        if ($userStartup -and (Test-Path -Path $userStartup -ErrorAction Stop)) {
            $userItems = Get-ChildItem -Path $userStartup -File -ErrorAction Stop
            foreach ($item in $userItems) {
                $results.Add([PSCustomObject]@{
                    Name      = $item.Name
                    Source    = "User Startup Folder"
                    Command   = $item.FullName
                    UserScope = $env:USERNAME
                    Status    = "Active"
                })
            }
        }
    }
    catch {
        $errors.Add("Startup folder notice: $($_.Exception.Message)")
    }

    # 4. Optional Scheduled Tasks (Logon or Boot triggered)
    if ($IncludeScheduledTasks) {
        try {
            $tasks = Get-ScheduledTask -ErrorAction Stop |
                Where-Object { $_.State -ne 'Disabled' } |
                Where-Object {
                    $_.Triggers | Where-Object { $_.CimClass.CimClassName -match 'Logon|Boot' }
                } | Select-Object -First 25

            foreach ($t in $tasks) {
                $exec = if ($t.Actions -and $t.Actions[0].Execute) { $t.Actions[0].Execute } else { "Task Engine" }
                $results.Add([PSCustomObject]@{
                    Name      = $t.TaskName
                    Source    = "Scheduled Task (Startup/Logon)"
                    Command   = $exec
                    UserScope = if ($t.Principal.UserId) { $t.Principal.UserId } else { "SYSTEM" }
                    Status    = [string]$t.State
                })
            }
        }
        catch {
            $errors.Add("Scheduled Tasks notice: $($_.Exception.Message)")
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No active startup applications detected."
    }

    if ($results.Count -eq 0 -and $errors.Count -gt 0) {
        $status = "warning"
        $summary = "Startup audit completed with access notices ($($errors.Count))."
    }
    else {
        $summary = "Discovered $($results.Count) active startup application(s) and logon entry(ies)."
    }
}
catch {
    $status = "error"
    $summary = "Failed to query startup applications: $($_.Exception.Message)"
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
