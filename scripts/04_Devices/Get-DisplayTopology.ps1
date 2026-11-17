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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Load Windows Forms assembly for Screen topology
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop

    # Query active GPU Controllers via CIM with registry fallback
    $gpuList = @()
    try {
        $gpuList = @(Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop)
    }
    catch {
        $gpuList = @()
    }

    $primaryGpu = "Generic Display Adapter"
    if ($gpuList.Count -gt 0 -and $gpuList[0].Name) {
        $primaryGpu = [string]$gpuList[0].Name
    }
    else {
        # Registry fallback for Display Adapter Name (safe .NET read-only open avoids ACL errors on Properties subkey)
        try {
            $dispKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey("SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}", $false)
            if ($dispKey) {
                foreach ($subName in $dispKey.GetSubKeyNames()) {
                    if ($subName -match '^\d{4}$') {
                        try {
                            $sub = $dispKey.OpenSubKey($subName, $false)
                            if ($sub) {
                                $desc = $sub.GetValue("DriverDesc")
                                $sub.Close()
                                if ($desc) {
                                    $primaryGpu = [string]$desc
                                    break
                                }
                            }
                        }
                        catch {}
                    }
                }
                $dispKey.Close()
            }
        }
        catch {}
    }

    $screens = [System.Windows.Forms.Screen]::AllScreens

    if ($screens -and $screens.Count -gt 0) {
        foreach ($scr in $screens) {
            $w = $scr.Bounds.Width
            $h = $scr.Bounds.Height
            $resStr = "${w}x${h}"
            $isPrim = if ($scr.Primary) { "True (Main)" } else { "False" }

            $hz = 60
            $matchingGpu = $gpuList | Where-Object { $_.CurrentHorizontalResolution -eq $w -and $_.CurrentVerticalResolution -eq $h } | Select-Object -First 1
            if ($matchingGpu -and $matchingGpu.CurrentRefreshRate) {
                $hz = [int]$matchingGpu.CurrentRefreshRate
            }

            $results.Add([PSCustomObject]@{
                DeviceName    = [string]$scr.DeviceName
                Resolution    = $resStr
                RefreshRateHz = $hz
                BitsPerPixel  = [int]$scr.BitsPerPixel
                IsPrimary     = $isPrim
                GPUAdapter    = if ($matchingGpu -and $matchingGpu.Name) { [string]$matchingGpu.Name } else { $primaryGpu }
            })
        }
    }

    # Human-readable table first
    if ($results.Count -gt 0) {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No active desktop monitors enumerated in current session."
    }

    $summary = "Detected $($results.Count) connected monitor(s) running under $primaryGpu."
}
catch {
    $status = "error"
    $summary = "Failed to query display topology: $($_.Exception.Message)"
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
