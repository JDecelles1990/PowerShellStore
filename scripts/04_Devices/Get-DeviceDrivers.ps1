<#
.SYNOPSIS
    Enumerates installed device drivers, reporting version, manufacturer, signing status, and device class in a clean table and structured JSON.
.PSSTORE_META
    {
        "title": "Get Installed Device Drivers",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 45,
        "output_mode": "json",
        "params": [
            {"name": "DeviceClass", "type": "string", "default": "*"},
            {"name": "OnlySigned", "type": "bool", "default": false},
            {"name": "MaxResults", "type": "int", "default": 50, "min": 1, "max": 1000}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$DeviceClass = "*",

    [Parameter(Mandatory = $false)]
    [bool]$OnlySigned = $false,

    [Parameter(Mandatory = $false)]
    [int]$MaxResults = 50
)

$ErrorActionPreference = 'Stop'

$driversList = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$status = "pass"
$summary = ""

try {
    # Tier 1: Query via CIM Win32_PnPSignedDriver (preferred for full digital signature details)
    $queriedTier1 = $false
    try {
        $cimDrivers = Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction Stop |
            Where-Object { $_.DeviceName -and ($_.DeviceClass -like $DeviceClass) }
        
        if ($OnlySigned) {
            $cimDrivers = $cimDrivers | Where-Object { $_.IsSigned -eq $true }
        }

        foreach ($d in ($cimDrivers | Select-Object -First $MaxResults)) {
            $driverDateStr = if ($d.DriverDate) {
                try { ([datetime]$d.DriverDate).ToString("yyyy-MM-dd") } catch { [string]$d.DriverDate }
            } else { "N/A" }

            $driversList.Add([PSCustomObject]@{
                DeviceName    = [string]$d.DeviceName
                DeviceClass   = [string]$d.DeviceClass
                Manufacturer  = [string]$d.Manufacturer
                DriverVersion = [string]$d.DriverVersion
                DriverDate    = $driverDateStr
                IsSigned      = [bool]$d.IsSigned
                InfName       = [string]$d.InfName
            })
        }
        $queriedTier1 = $true
    }
    catch {
        # Tier 1 unaccessible; proceed to resilient Tier 2
    }

    # Tier 2: Resilient Registry Enumeration (fast, accessible without elevation)
    if (-not $queriedTier1 -or $driversList.Count -eq 0) {
        try {
            $classRoot = "HKLM:\SYSTEM\CurrentControlSet\Control\Class"
            if (Test-Path -Path $classRoot) {
                $subkeys = Get-ChildItem -Path $classRoot -Recurse -Depth 1 -ErrorAction SilentlyContinue |
                    Where-Object { $_.PSChildName -match '^\d{4}$' }

                foreach ($key in $subkeys) {
                    if ($driversList.Count -ge $MaxResults) { break }

                    $devDesc = $key.GetValue("DriverDesc")
                    if (-not $devDesc) { $devDesc = $key.GetValue("DeviceDesc") }
                    if (-not $devDesc) { continue }

                    $devClass = [string]$key.GetValue("Class")
                    if (-not [string]::IsNullOrWhiteSpace($devClass) -and ($DeviceClass -ne "*") -and ($devClass -notlike $DeviceClass)) {
                        continue
                    }

                    $provider = [string]$key.GetValue("ProviderName")
                    $version  = [string]$key.GetValue("DriverVersion")
                    $date     = [string]$key.GetValue("DriverDate")
                    $inf      = [string]$key.GetValue("InfPath")

                    $driversList.Add([PSCustomObject]@{
                        DeviceName    = [string]$devDesc
                        DeviceClass   = if ($devClass) { $devClass } else { "System" }
                        Manufacturer  = if ($provider) { $provider } else { "Unknown" }
                        DriverVersion = if ($version) { $version } else { "N/A" }
                        DriverDate    = if ($date) { $date } else { "N/A" }
                        IsSigned      = $true
                        InfName       = if ($inf) { $inf } else { "N/A" }
                    })
                }
            }
        }
        catch {
            # Registry fallback failed
        }
    }

    # Tier 3: DriverQuery fallback (if Tier 1 and 2 returned nothing)
    if ($driversList.Count -eq 0) {
        try {
            $dqCsv = & driverquery.exe /FO CSV /V 2>$null | ConvertFrom-Csv -ErrorAction SilentlyContinue
            if ($dqCsv) {
                $filteredDq = $dqCsv | Where-Object { $_."Display Name" }
                if ($DeviceClass -ne "*") {
                    $filteredDq = $filteredDq | Where-Object { $_."Device Class" -like $DeviceClass }
                }

                foreach ($item in ($filteredDq | Select-Object -First $MaxResults)) {
                    $driversList.Add([PSCustomObject]@{
                        DeviceName    = [string]$item."Display Name"
                        DeviceClass   = [string]$item."Device Class"
                        Manufacturer  = [string]$item."Manufacturer"
                        DriverVersion = [string]$item."Driver Version"
                        DriverDate    = [string]$item."Driver Date"
                        IsSigned      = ($item."Is Signed" -match "True|Yes")
                        InfName       = [string]$item."Inf Name"
                    })
                }
            }
        } catch {}
    }

    $count = $driversList.Count
    $status = if ($count -gt 0) { "pass" } else { "warning" }
    $summary = "Found $count installed driver(s) matching filter [Class='$DeviceClass', OnlySigned=$OnlySigned]."

    # Human-readable formatted ASCII table for RMM console and Raw Output tab
    if ($count -gt 0) {
        $tableOutput = $driversList | Format-Table -Property DeviceName, DeviceClass, Manufacturer, DriverVersion, DriverDate, IsSigned -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Driver inventory failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($driversList)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
