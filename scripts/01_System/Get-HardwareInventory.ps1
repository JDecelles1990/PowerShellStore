<#
.SYNOPSIS
    Gathers detailed hardware specifications including processor, RAM capacity, graphics adapters, motherboard, and BIOS revision.
.PSSTORE_META
    {
        "title": "Get Hardware & BIOS Inventory",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "IncludeGPU", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeGPU = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$hardwareRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # 1. Query Processor Details
    $cpuPath = "HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    $cpuName = "Unknown CPU"
    $cpuClock = "Unknown"
    if (Test-Path $cpuPath) {
        $cpuProps = Get-ItemProperty -Path $cpuPath -ErrorAction SilentlyContinue
        if ($cpuProps.ProcessorNameString) { $cpuName = $cpuProps.ProcessorNameString.Trim() }
        if ($cpuProps."~MHz") { $cpuClock = "$($cpuProps.'~MHz') MHz" }
    }
    $logicalCores = [System.Environment]::ProcessorCount

    # 2. Query Memory via .NET ComputerInfo
    Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue
    $compInfo = New-Object Microsoft.VisualBasic.Devices.ComputerInfo
    $totalRamGb = [math]::Round($compInfo.TotalPhysicalMemory / 1GB, 2)
    $freeRamGb = [math]::Round($compInfo.AvailablePhysicalMemory / 1GB, 2)
    $usedRamGb = [math]::Round($totalRamGb - $freeRamGb, 2)
    $pctUsed = [math]::Round(($usedRamGb / $totalRamGb) * 100, 1)

    # 3. Query BIOS and Motherboard
    $biosPath = "HKLM:\HARDWARE\DESCRIPTION\System\BIOS"
    $sysMfr = "Unknown"
    $sysModel = "Unknown"
    $biosVer = "Unknown"
    $biosDate = "Unknown"
    $boardModel = "Unknown"
    if (Test-Path $biosPath) {
        $bProps = Get-ItemProperty -Path $biosPath -ErrorAction SilentlyContinue
        if ($bProps.SystemManufacturer) { $sysMfr = $bProps.SystemManufacturer.Trim() }
        if ($bProps.SystemProductName) { $sysModel = $bProps.SystemProductName.Trim() }
        if ($bProps.BIOSVersion) { $biosVer = $bProps.BIOSVersion.Trim() }
        if ($bProps.BIOSReleaseDate) { $biosDate = $bProps.BIOSReleaseDate.Trim() }
        if ($bProps.BaseBoardProduct) { $boardModel = $bProps.BaseBoardProduct.Trim() }
    }

    # 4. Query GPU / Display Adapters
    $gpuList = [System.Collections.Generic.List[string]]::new()
    if ($IncludeGPU) {
        $displayClass = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        if (Test-Path $displayClass) {
            $gpuKeys = Get-ChildItem -Path $displayClass -ErrorAction SilentlyContinue |
                Where-Object { $_.PSChildName -match '^\d{4}$' }
            foreach ($gk in $gpuKeys) {
                $desc = $gk.GetValue("DriverDesc")
                if ($desc -and -not $gpuList.Contains($desc)) {
                    $gpuList.Add($desc)
                }
            }
        }
    }
    $gpuSummary = if ($gpuList.Count -gt 0) { ($gpuList -join ", ") } else { "None detected" }

    $summary = "$sysMfr $sysModel | CPU: $cpuName ($logicalCores threads) | RAM: ${totalRamGb} GB (${pctUsed}% used) | GPU: $gpuSummary"

    $hwObj = [PSCustomObject]@{
        Manufacturer        = $sysMfr
        ProductModel        = $sysModel
        Motherboard         = $boardModel
        BIOSVersion         = $biosVer
        BIOSReleaseDate     = $biosDate
        ProcessorName       = $cpuName
        LogicalProcessors   = $logicalCores
        ProcessorClock      = $cpuClock
        TotalMemoryGB       = $totalRamGb
        FreeMemoryGB        = $freeRamGb
        MemoryUsagePercent  = "$pctUsed%"
        GraphicsAdapter     = $gpuSummary
    }
    $hardwareRecords.Add($hwObj)

    # Human-Readable ASCII Table Output
    $displayRows = @(
        [PSCustomObject]@{ Component = "System Model"; Specification = "$sysMfr $sysModel" },
        [PSCustomObject]@{ Component = "Motherboard"; Specification = $boardModel },
        [PSCustomObject]@{ Component = "BIOS Version"; Specification = "$biosVer ($biosDate)" },
        [PSCustomObject]@{ Component = "Processor"; Specification = "$cpuName ($logicalCores vCPUs @ $cpuClock)" },
        [PSCustomObject]@{ Component = "Physical Memory"; Specification = "${totalRamGb} GB Total (${freeRamGb} GB Free, ${pctUsed}% in use)" },
        [PSCustomObject]@{ Component = "Graphics Adapter"; Specification = $gpuSummary }
    )
    $tableOutput = $displayRows | Format-Table -AutoSize | Out-String
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Failed to query hardware inventory: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($hardwareRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}

