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

try {
    $results = @()

    # 1. Inspect HKCU Run key
    $hkcuRunPath = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    if (Test-Path $hkcuRunPath) {
        $hkcuProps = Get-ItemProperty -Path $hkcuRunPath -ErrorAction SilentlyContinue
        if ($hkcuProps) {
            foreach ($propName in $hkcuProps.PSObject.Properties.Name) {
                if ($propName -notmatch '^PS.*') {
                    $results += [PSCustomObject]@{
                        Name      = $propName
                        Source    = "Registry HKCU:Run"
                        Command   = [string]$hkcuProps.$propName
                        UserScope = $env:USERNAME
                        Status    = "Active"
                    }
                }
            }
        }
    }

    # 2. Inspect HKLM Run key (System-wide)
    $hklmRunPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    if (Test-Path $hklmRunPath) {
        $hklmProps = Get-ItemProperty -Path $hklmRunPath -ErrorAction SilentlyContinue
        if ($hklmProps) {
            foreach ($propName in $hklmProps.PSObject.Properties.Name) {
                if ($propName -notmatch '^PS.*') {
                    $results += [PSCustomObject]@{
                        Name      = $propName
                        Source    = "Registry HKLM:Run"
                        Command   = [string]$hklmProps.$propName
                        UserScope = "All Users"
                        Status    = "Active"
                    }
                }
            }
        }
    }

    # 3. Inspect User Startup Folder
    $userStartup = [Environment]::GetFolderPath('Startup')
    if (Test-Path $userStartup) {
        $userItems = Get-ChildItem -Path $userStartup -File -ErrorAction SilentlyContinue
        foreach ($item in $userItems) {
            $results += [PSCustomObject]@{
                Name      = $item.Name
                Source    = "User Startup Folder"
                Command   = $item.FullName
                UserScope = $env:USERNAME
                Status    = "Active"
            }
        }
    }

    # 4. Optional Scheduled Tasks (Logon triggered)
    if ($IncludeScheduledTasks) {
        $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue |
            Where-Object { $_.State -ne 'Disabled' } |
            Where-Object {
                $_.Triggers | Where-Object { $_ -is [Microsoft.PowerShell.Cmdletization.GeneratedTypes.ScheduledTask.TaskTrigger] -or $_.CimClass.CimClassName -match 'Logon' }
            } | Select-Object -First 20

        foreach ($t in $tasks) {
            $exec = if ($t.Actions -and $t.Actions[0].Execute) { $t.Actions[0].Execute } else { "Task Engine" }
            $results += [PSCustomObject]@{
                Name      = $t.TaskName
                Source    = "Scheduled Task (Logon)"
                Command   = $exec
                UserScope = if ($t.Principal.UserId) { $t.Principal.UserId } else { "SYSTEM" }
                Status    = [string]$t.State
            }
        }
    }

    # Human-readable table first
    $results | Format-Table -AutoSize | Out-String | Write-Output

    $payload = @{
        status  = "pass"
        summary = "Discovered $($results.Count) active startup application(s) and logon entry(ies)."
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query startup applications: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

