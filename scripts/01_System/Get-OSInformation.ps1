<#
.SYNOPSIS
    Gathers comprehensive operating system information including edition, version, build number, install date, uptime, and pending reboot state.
.PSSTORE_META
    {
        "title": "Get Operating System Information",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "Detailed", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$Detailed = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # 1. Read OS Details from Registry (safe, fast, accessible without elevation)
    $cvPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    $cvProps = Get-ItemProperty -Path $cvPath -ErrorAction Stop

    $rawProdName = [string]$cvProps.ProductName
    $editionId = [string]$cvProps.EditionID
    $displayVer = if ($cvProps.DisplayVersion) { [string]$cvProps.DisplayVersion } elseif ($cvProps.ReleaseId) { [string]$cvProps.ReleaseId } else { "N/A" }
    $currentBuild = [int]$cvProps.CurrentBuildNumber
    $ubr = if ($cvProps.UBR) { [int]$cvProps.UBR } else { 0 }
    $fullBuild = "$currentBuild.$ubr"

    # Distinguish Windows 11 from Windows 10
    $osName = $rawProdName
    if ($currentBuild -ge 22000 -and $rawProdName -like "*Windows 10*") {
        $osName = $rawProdName -replace "Windows 10", "Windows 11"
    }

    # 2. Compute Uptime and Last Boot Time
    $upMs = [long][System.Environment]::TickCount64
    $upSpan = [System.TimeSpan]::FromMilliseconds($upMs)
    $uptimeStr = "$($upSpan.Days)d $($upSpan.Hours)h $($upSpan.Minutes)m"
    $lastBootTime = (Get-Date).AddMilliseconds(-$upMs).ToString("yyyy-MM-dd HH:mm:ss")

    # 3. Format Install Date
    $installDateStr = "N/A"
    if ($cvProps.InstallDate) {
        try {
            $installDateStr = [DateTimeOffset]::FromUnixTimeSeconds([long]$cvProps.InstallDate).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss")
        } catch {}
    }

    # 4. Check Pending Reboot Status
    $rebootPending = $false
    $cbsReboot = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending" -ErrorAction SilentlyContinue
    $wuReboot = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired" -ErrorAction SilentlyContinue
    if ($cbsReboot -or $wuReboot) {
        $rebootPending = $true
    }

    # 5. Architecture & System Info
    $is64 = [System.Environment]::Is64BitOperatingSystem
    $arch = if ($is64) { "64-bit ($($env:PROCESSOR_ARCHITECTURE))" } else { "32-bit" }
    $sysDrive = [System.Environment]::GetEnvironmentVariable("SystemDrive")
    $sysRoot = [System.Environment]::GetEnvironmentVariable("SystemRoot")

    # 6. Detailed optional attributes (Hotfix count, Registered Owner)
    $hotfixCount = 0
    if ($Detailed) {
        try {
            $qfes = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\HotFix" -ErrorAction SilentlyContinue
            if ($qfes) { $hotfixCount = ($qfes | Measure-Object).Count }
        } catch {}
    }

    $owner = if ($cvProps.RegisteredOwner) { [string]$cvProps.RegisteredOwner } else { "N/A" }
    $org = if ($cvProps.RegisteredOrganization) { [string]$cvProps.RegisteredOrganization } else { "N/A" }

    $summary = "$osName ($displayVer, Build $fullBuild) | Uptime: $uptimeStr | Reboot Pending: $rebootPending"

    $osObj = [PSCustomObject]@{
        ComputerName      = [string]$env:COMPUTERNAME
        OperatingSystem   = $osName
        Edition           = $editionId
        DisplayVersion    = $displayVer
        BuildNumber       = $fullBuild
        Architecture      = $arch
        Uptime            = $uptimeStr
        LastBootTime      = $lastBootTime
        InstallDate       = $installDateStr
        PendingReboot     = $rebootPending
        SystemDirectory   = $sysRoot
        RegisteredOwner   = $owner
    }
    $results.Add($osObj)

    # Human-Readable Table / Summary for RMM and Console
    $tableData = @(
        [PSCustomObject]@{ Property = "Computer Name"; Value = $env:COMPUTERNAME },
        [PSCustomObject]@{ Property = "Operating System"; Value = $osName },
        [PSCustomObject]@{ Property = "Display Version"; Value = $displayVer },
        [PSCustomObject]@{ Property = "Full Build"; Value = $fullBuild },
        [PSCustomObject]@{ Property = "Architecture"; Value = $arch },
        [PSCustomObject]@{ Property = "Uptime"; Value = $uptimeStr },
        [PSCustomObject]@{ Property = "Last Boot Time"; Value = $lastBootTime },
        [PSCustomObject]@{ Property = "Install Date"; Value = $installDateStr },
        [PSCustomObject]@{ Property = "Pending Reboot"; Value = $rebootPending },
        [PSCustomObject]@{ Property = "System Directory"; Value = $sysRoot },
        [PSCustomObject]@{ Property = "Registered Owner"; Value = $owner }
    )
    $tableOutput = $tableData | Format-Table -AutoSize | Out-String
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Failed to query operating system information: $($_.Exception.Message)"
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
