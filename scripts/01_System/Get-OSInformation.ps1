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

    # 2. Compute accurate Uptime & Last Boot Time (PowerShell 5.1 compatible)
    $lastBootDt = $null
    try {
        $cimOs = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        if ($cimOs -and $cimOs.LastBootUpTime) {
            $lastBootDt = [datetime]$cimOs.LastBootUpTime
        }
    }
    catch {
        # Fallback if CIM is inaccessible: high-res monotonic counter or TickCount
    }

    if ($null -eq $lastBootDt) {
        if ([System.Diagnostics.Stopwatch]::IsHighResolution -and [System.Diagnostics.Stopwatch]::Frequency -gt 0) {
            $upSeconds = [double][System.Diagnostics.Stopwatch]::GetTimestamp() / [double][System.Diagnostics.Stopwatch]::Frequency
            $upSpan = [System.TimeSpan]::FromSeconds($upSeconds)
        }
        else {
            $upMs = [double][uint32][System.Environment]::TickCount
            $upSpan = [System.TimeSpan]::FromMilliseconds($upMs)
        }
        $lastBootDt = (Get-Date).Subtract($upSpan)
    }
    else {
        $upSpan = (Get-Date).Subtract($lastBootDt)
    }

    $uptimeStr = "$($upSpan.Days)d $($upSpan.Hours)h $($upSpan.Minutes)m"
    $lastBootTime = $lastBootDt.ToString("yyyy-MM-dd HH:mm:ss")

    # 3. Format Install Date
    $installDateStr = "N/A"
    if ($cvProps.InstallDate) {
        try {
            $installDateStr = [DateTimeOffset]::FromUnixTimeSeconds([long]$cvProps.InstallDate).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss")
        }
        catch {}
    }

    # 4. Check Pending Reboot Status
    $rebootPending = $false
    $cbsReboot = Test-Path -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending" -ErrorAction Stop
    $wuReboot = Test-Path -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired" -ErrorAction Stop
    if ($cbsReboot -or $wuReboot) {
        $rebootPending = $true
    }

    # 5. Architecture & System Info
    $is64 = [System.Environment]::Is64BitOperatingSystem
    $arch = if ($is64) { "64-bit ($($env:PROCESSOR_ARCHITECTURE))" } else { "32-bit" }
    $sysRoot = [System.Environment]::GetEnvironmentVariable("SystemRoot")
    $owner = if ($cvProps.RegisteredOwner) { [string]$cvProps.RegisteredOwner } else { "N/A" }

    $summary = "$osName ($displayVer, Build $fullBuild) | Uptime: $uptimeStr | Reboot Pending: $rebootPending"

    if ($Detailed) {
        $org = if ($cvProps.RegisteredOrganization) { [string]$cvProps.RegisteredOrganization } else { "N/A" }
        $hotfixCount = 0
        try {
            $qfes = Get-HotFix -ErrorAction Stop
            if ($qfes) { $hotfixCount = @($qfes).Count }
        }
        catch {
            $hotfixCount = 0
        }

        $osObj = [PSCustomObject]@{
            ComputerName           = [string]$env:COMPUTERNAME
            OperatingSystem        = $osName
            Edition                = $editionId
            DisplayVersion         = $displayVer
            BuildNumber            = $fullBuild
            Architecture           = $arch
            Uptime                 = $uptimeStr
            LastBootTime           = $lastBootTime
            InstallDate            = $installDateStr
            PendingReboot          = $rebootPending
            SystemDirectory        = $sysRoot
            RegisteredOwner        = $owner
            RegisteredOrganization = $org
            InstalledHotfixes      = $hotfixCount
        }
        $results.Add($osObj)

        $tableData = @(
            [PSCustomObject]@{ Property = "Computer Name"; Value = $env:COMPUTERNAME },
            [PSCustomObject]@{ Property = "Operating System"; Value = $osName },
            [PSCustomObject]@{ Property = "Edition"; Value = $editionId },
            [PSCustomObject]@{ Property = "Display Version"; Value = $displayVer },
            [PSCustomObject]@{ Property = "Full Build"; Value = $fullBuild },
            [PSCustomObject]@{ Property = "Architecture"; Value = $arch },
            [PSCustomObject]@{ Property = "Uptime"; Value = $uptimeStr },
            [PSCustomObject]@{ Property = "Last Boot Time"; Value = $lastBootTime },
            [PSCustomObject]@{ Property = "Install Date"; Value = $installDateStr },
            [PSCustomObject]@{ Property = "Pending Reboot"; Value = $rebootPending },
            [PSCustomObject]@{ Property = "System Directory"; Value = $sysRoot },
            [PSCustomObject]@{ Property = "Registered Owner"; Value = $owner },
            [PSCustomObject]@{ Property = "Registered Organization"; Value = $org },
            [PSCustomObject]@{ Property = "Installed Hotfixes"; Value = $hotfixCount }
        )
    }
    else {
        $osObj = [PSCustomObject]@{
            ComputerName    = [string]$env:COMPUTERNAME
            OperatingSystem = $osName
            DisplayVersion  = $displayVer
            BuildNumber     = $fullBuild
            Uptime          = $uptimeStr
            PendingReboot   = $rebootPending
        }
        $results.Add($osObj)

        $tableData = @(
            [PSCustomObject]@{ Property = "Computer Name"; Value = $env:COMPUTERNAME },
            [PSCustomObject]@{ Property = "Operating System"; Value = $osName },
            [PSCustomObject]@{ Property = "Display Version"; Value = $displayVer },
            [PSCustomObject]@{ Property = "Full Build"; Value = $fullBuild },
            [PSCustomObject]@{ Property = "Uptime"; Value = $uptimeStr },
            [PSCustomObject]@{ Property = "Pending Reboot"; Value = $rebootPending }
        )
    }

    # Human-Readable Table / Summary for RMM and Console
    $tableOutput = $tableData | Format-Table -AutoSize | Out-String -Width 4096
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
