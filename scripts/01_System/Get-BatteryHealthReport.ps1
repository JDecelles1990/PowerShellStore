<#
.SYNOPSIS
    Queries system battery metrics, charge status, design vs. full charge capacity, cycle count, and calculated wear percentage.
.PSSTORE_META
    {
        "title": "Get Battery Health & Power Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "WearThresholdPercent", "type": "int", "default": 30, "min": 5, "max": 80}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$WearThresholdPercent = 30
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$batteryRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Tier 1: Fast .NET PowerStatus Inspection (works in all user contexts)
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
    $pStatus = [System.Windows.Forms.SystemInformation]::PowerStatus

    $chargeState = [string]$pStatus.BatteryChargeStatus
    $powerLine = [string]$pStatus.PowerLineStatus
    $pctRemaining = [math]::Round([double]$pStatus.BatteryLifePercent * 100, 1)

    if ($chargeState -match "NoSystemBattery") {
        $status = "pass"
        $summary = "System is a desktop PC or virtual machine (no battery installed)."
        $batteryRecords.Add([PSCustomObject]@{
            DeviceType           = "Desktop / Virtual Machine"
            PowerLineStatus      = $powerLine
            BatteryInstalled     = $false
            ChargeRemaining      = "N/A"
            DesignCapacityMWh    = "N/A"
            FullChargeCapacityMWh= "N/A"
            WearLevelPercent     = "0%"
            CycleCount           = "N/A"
            HealthStatus         = "N/A (AC Powered)"
        })
    }
    else {
        # Laptop / Battery-backed device detected
        $designCap = 0
        $fullCap = 0
        $cycleCount = "N/A"
        $chemistry = "Lithium-Ion"

        # Tier 2: Attempt powercfg XML report if elevated or accessible
        $tempXml = Join-Path -Path $env:TEMP -ChildPath "psstore_bat_$([System.IO.Path]::GetRandomFileName()).xml"
        try {
            & powercfg.exe /batteryreport /xml /output $tempXml 2>$null | Out-Null
            if (Test-Path -Path $tempXml) {
                [xml]$xmlReport = Get-Content -Path $tempXml -Raw -ErrorAction Stop
                $batNode = $xmlReport.BatteryReport.Batteries.Battery | Select-Object -First 1
                if ($batNode) {
                    if ($batNode.DesignCapacity) { $designCap = [long]$batNode.DesignCapacity }
                    if ($batNode.FullChargeCapacity) { $fullCap = [long]$batNode.FullChargeCapacity }
                    if ($batNode.CycleCount) { $cycleCount = [string]$batNode.CycleCount }
                    if ($batNode.Chemistry) { $chemistry = [string]$batNode.Chemistry }
                }
            }
        }
        catch {}
        finally {
            if (Test-Path -Path $tempXml) {
                Remove-Item -Path $tempXml -Force -ErrorAction SilentlyContinue
            }
        }

        # Calculate Wear Level
        $wearPct = 0
        if ($designCap -gt 0 -and $fullCap -gt 0) {
            $wear = (1.0 - ($fullCap / $designCap)) * 100.0
            $wearPct = [math]::Max(0.0, [math]::Round($wear, 1))
        }

        $healthStatus = "Good"
        if ($wearPct -ge $WearThresholdPercent) {
            $status = "warning"
            $healthStatus = "Degraded (Wear exceeds ${WearThresholdPercent}%)"
            $summary = "Warning: Battery wear is at ${wearPct}% (exceeds threshold of ${WearThresholdPercent}%)."
        } else {
            $status = "pass"
            $summary = "Battery is healthy. Current charge: ${pctRemaining}%, Wear: ${wearPct}%, Power: $powerLine."
        }

        $batteryRecords.Add([PSCustomObject]@{
            DeviceType           = "Laptop / Portable"
            PowerLineStatus      = $powerLine
            BatteryInstalled     = $true
            ChargeRemaining      = "$pctRemaining%"
            DesignCapacityMWh    = if ($designCap -gt 0) { "$designCap mWh" } else { "Query requires elevation" }
            FullChargeCapacityMWh= if ($fullCap -gt 0) { "$fullCap mWh" } else { "Query requires elevation" }
            WearLevelPercent     = "$wearPct%"
            CycleCount           = $cycleCount
            HealthStatus         = $healthStatus
        })
    }

    # Human-Readable Formatted Table for RMM and Console
    if ($batteryRecords.Count -gt 0) {
        $tableOutput = $batteryRecords | Format-Table -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Failed to query battery health: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($batteryRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
