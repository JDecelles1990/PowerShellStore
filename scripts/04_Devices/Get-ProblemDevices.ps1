<#
.SYNOPSIS
    Scans Device Manager for hardware components reporting error codes, missing drivers, or failures.
.PSSTORE_META
    {
        "title": "Get Problem Devices (Device Manager Errors)",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "IncludeDisabled", "type": "bool", "default": false}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeDisabled = $false
)

$ErrorActionPreference = 'Stop'

try {
    # Query PnP devices reporting non-zero config error codes
    $devices = Get-CimInstance -ClassName Win32_PnPEntity -Filter "ConfigManagerErrorCode <> 0" -ErrorAction Stop

    $errorMap = @{
        1  = "Device is not configured correctly (Code 1)"
        10 = "This device cannot start (Code 10)"
        14 = "This device cannot work properly until restart (Code 14)"
        18 = "Reinstall the drivers for this device (Code 18)"
        22 = "This device is disabled (Code 22)"
        28 = "Drivers for this device are not installed (Code 28)"
        31 = "This device is not working properly (Code 31)"
        39 = "Windows cannot load the device driver (Code 39)"
        43 = "Windows has stopped this device because it reported problems (Code 43)"
    }

    $results = @()
    foreach ($dev in $devices) {
        $code = [int]$dev.ConfigManagerErrorCode
        if (-not $IncludeDisabled -and $code -eq 22) {
            continue
        }

        $desc = if ($errorMap.ContainsKey($code)) {
            $errorMap[$code]
        } else {
            "Hardware Error Code $code"
        }

        $results += [PSCustomObject]@{
            DeviceName       = if ($dev.Name) { $dev.Name } else { "Unknown Device" }
            DeviceID         = $dev.DeviceID
            ErrorCode        = $code
            ErrorDescription = $desc
            DeviceClass      = if ($dev.PNPClass) { $dev.PNPClass } else { "Unclassified" }
            Manufacturer     = if ($dev.Manufacturer) { $dev.Manufacturer } else { "Unknown" }
        }
    }

    if ($results.Count -eq 0) {
        Write-Output "No problem devices or hardware error codes detected in Device Manager."
        $payload = @{
            status  = "pass"
            summary = "Hardware health is clear: 0 devices reporting error codes in Device Manager."
            data    = @()
            errors  = @()
        }
    }
    else {
        # Human-readable table first
        $results | Format-Table -AutoSize | Out-String | Write-Output

        $payload = @{
            status  = "warning"
            summary = "Found $($results.Count) device(s) reporting error codes or missing drivers."
            data    = @($results)
            errors  = @()
        }
    }

    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to scan problem devices: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

