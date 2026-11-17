<#
.SYNOPSIS
    Audits active Wi-Fi connection health, SSID, signal strength, radio type, channel, link speed, and gateway latency.
.PSSTORE_META
    {
        "title": "Get Wi-Fi Health & Signal Diagnostics",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 25,
        "output_mode": "json",
        "params": [
            {"name": "PingGateway", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$PingGateway = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Query Wi-Fi interfaces using native netsh
    $netshOut = & netsh.exe wlan show interfaces 2>&1
    $netshExit = $LASTEXITCODE
    $netshText = ($netshOut | Out-String)

    # Detect absent Wi-Fi hardware or disabled WLAN AutoConfig service
    $hasNoWlan = (
        $netshExit -ne 0 -or
        $netshText -match 'not found|no wireless interface|not running'
    )

    if ($hasNoWlan) {
        $summary = "No active wireless network interface or WLAN AutoConfig service detected on this system."
        $results.Add([PSCustomObject]@{
            InterfaceName    = "None"
            State            = "No Wi-Fi Hardware / WLAN Inactive"
            SSID             = "N/A"
            BSSID            = "N/A"
            SignalPercent    = 0
            RadioType        = "N/A"
            Channel          = 0
            ReceiveRateMbps  = "0"
            TransmitRateMbps = "0"
            GatewayLatencyMs = "N/A"
        })
    }
    else {
        # Extract fields from multiline netsh output using (?m) multiline mode
        $extractField = {
            param([string]$regex, [string]$text)
            if ($text -match $regex) { $Matches[1].Trim() } else { "N/A" }
        }

        $state     = & $extractField '(?m)^\s*State\s*:\s*([^\r\n]+)' $netshText
        $name      = & $extractField '(?m)^\s*Name\s*:\s*([^\r\n]+)' $netshText
        $ssid      = & $extractField '(?m)^\s*SSID\s*:\s*([^\r\n]+)' $netshText
        $bssid     = & $extractField '(?m)^\s*BSSID\s*:\s*([^\r\n]+)' $netshText
        $radio     = & $extractField '(?m)^\s*Radio type\s*:\s*([^\r\n]+)' $netshText
        $channel   = & $extractField '(?m)^\s*Channel\s*:\s*([^\r\n]+)' $netshText
        $signalStr = & $extractField '(?m)^\s*Signal\s*:\s*(\d+)%' $netshText
        $rxRate    = & $extractField '(?m)^\s*Receive rate \(Mbps\)\s*:\s*([^\r\n]+)' $netshText
        $txRate    = & $extractField '(?m)^\s*Transmit rate \(Mbps\)\s*:\s*([^\r\n]+)' $netshText

        $signalVal = if ($signalStr -match '^\d+$') { [int]$signalStr } else { 0 }
        $gwLatency = "N/A"

        if ($PingGateway -and $state -eq "connected") {
            try {
                $gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop | Select-Object -First 1).NextHop
                if ($gw) {
                    $pinger = New-Object System.Net.NetworkInformation.Ping
                    $samples = @()
                    for ($i = 0; $i -lt 3; $i++) {
                        $reply = $pinger.Send($gw, 1500)
                        if ($reply.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                            $samples += [double]$reply.RoundtripTime
                        }
                    }
                    if ($samples.Count -gt 0) {
                        $avg = ($samples | Measure-Object -Average).Average
                        $gwLatency = "$([math]::Round($avg, 1)) ms"
                    }
                }
            }
            catch {
                $gwLatency = "Unreachable"
            }
        }

        $results.Add([PSCustomObject]@{
            InterfaceName    = $name
            State            = $state
            SSID             = $ssid
            BSSID            = $bssid
            SignalPercent    = $signalVal
            RadioType        = $radio
            Channel          = if ($channel -match '^\d+$') { [int]$channel } else { 0 }
            ReceiveRateMbps  = $rxRate
            TransmitRateMbps = $txRate
            GatewayLatencyMs = $gwLatency
        })

        if ($state -eq "connected" -and $signalVal -ge 50) {
            $status = "pass"
            $summary = "Connected to '$ssid' ($signalVal% signal, Channel $channel, Radio $radio, Gateway Latency: $gwLatency)."
        } elseif ($state -eq "connected" -and $signalVal -lt 50) {
            $status = "warning"
            $summary = "Weak Wi-Fi signal on '$ssid' ($signalVal% signal, Channel $channel, Radio $radio)."
        } else {
            $status = "pass"
            $summary = "Wireless interface '$name' is present in state '$state'."
        }
    }

    # Human-readable table first
    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Failed to query Wi-Fi diagnostics: $($_.Exception.Message)"
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
