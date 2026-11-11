<#
.SYNOPSIS
    Audits connected displays, active desktop resolutions, refresh rates, and GPU adapter assignments.
.PSSTORE_META
    {
        "title": "Get Display & Monitor Topology",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": []
    }
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

try {
    # Load Windows Forms assembly for Screen topology
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue

    # Query active GPU Controllers
    $gpuList = @(Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue)
    $primaryGpu = if ($gpuList.Count -gt 0) { $gpuList[0].Name } else { "Generic Display Adapter" }

    $screens = [System.Windows.Forms.Screen]::AllScreens
    $results = @()

    foreach ($scr in $screens) {
        $w = $scr.Bounds.Width
        $h = $scr.Bounds.Height
        $resStr = "${w}x${h}"
        $isPrim = if ($scr.Primary) { "True (Main)" } else { "False" }

        # Match GPU refresh rate from WMI if available
        $hz = 60
        $matchingGpu = $gpuList | Where-Object { $_.CurrentHorizontalResolution -eq $w -and $_.CurrentVerticalResolution -eq $h } | Select-Object -First 1
        if ($matchingGpu -and $matchingGpu.CurrentRefreshRate) {
            $hz = [int]$matchingGpu.CurrentRefreshRate
        }

        $results += [PSCustomObject]@{
            DeviceName     = $scr.DeviceName
            Resolution     = $resStr
            RefreshRateHz  = $hz
            BitsPerPixel   = $scr.BitsPerPixel
            IsPrimary      = $isPrim
            GPUAdapter     = if ($matchingGpu) { $matchingGpu.Name } else { $primaryGpu }
        }
    }

    # Human-readable table first
    $results | Format-Table -AutoSize | Out-String | Write-Output

    $screenCount = $results.Count
    $payload = @{
        status  = "pass"
        summary = "Detected $screenCount connected monitor(s) running under $primaryGpu."
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query display topology: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

