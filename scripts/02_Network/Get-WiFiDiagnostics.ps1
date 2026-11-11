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

try {
    # Query Wi-Fi interfaces using native netsh
    $netshOut = netsh wlan show interfaces
    $netshText = $netshOut -join "`n"

    $results = @()

    if ($netshText -match 'There is no wireless interface on the system') {
        Write-Output "No wireless interface detected on this system (Ethernet or Virtual Machine)."
        $payload = @{
            status  = "pass"
            summary = "No wireless network interface detected on this system."
            data    = @([PSCustomObject]@{
                InterfaceName    = "None"
                State            = "No Wi-Fi Hardware"
                SSID             = "N/A"
                BSSID            = "N/A"
                SignalPercent    = 0
                RadioType        = "N/A"
                Channel          = 0
                ReceiveRateMbps  = 0
                TransmitRateMbps = 0
                GatewayLatencyMs = "N/A"
            })
            errors  = @()
        }
        $payload | ConvertTo-Json -Depth 4 -Compress
        exit 0
    }

    # Extract fields from netsh interface output
    $extractField = {
        param($regex, $text)
        if ($text -match $regex) { $matches[1].Trim() } else { "N/A" }
    }

    $state = & $extractField '^\s*State\s*:\s*(.+)$' $netshText
    $name = & $extractField '^\s*Name\s*:\s*(.+)$' $netshText
    $ssid = & $extractField '^\s*SSID\s*:\s*(.+)$' $netshText
    $bssid = & $extractField '^\s*BSSID\s*:\s*(.+)$' $netshText
    $radio = & $extractField '^\s*Radio type\s*:\s*(.+)$' $netshText
    $channel = & $extractField '^\s*Channel\s*:\s*(.+)$' $netshText
    $signalStr = & $extractField '^\s*Signal\s*:\s*(\d+)%' $netshText
    $rxRate = & $extractField '^\s*Receive rate \(Mbps\)\s*:\s*(.+)$' $netshText
    $txRate = & $extractField '^\s*Transmit rate \(Mbps\)\s*:\s*(.+)$' $netshText

    $signalVal = if ($signalStr -match '^\d+$') { [int]$signalStr } else { 0 }
    $gwLatency = "N/A"

    if ($PingGateway -and $state -eq "connected") {
        $gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop
        if ($gw) {
            $pings = Test-Connection -ComputerName $gw -Count 3 -ErrorAction SilentlyContinue
            if ($pings) {
                $avg = ($pings | Measure-Object -Property ResponseTime -Average).Average
                $gwLatency = "$([math]::Round($avg, 1)) ms"
            }
        }
    }

    $entry = [PSCustomObject]@{
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
    }
    $results += $entry

    # Human-readable table first
    $results | Format-Table -AutoSize | Out-String | Write-Output

    $statusOutcome = if ($state -eq "connected" -and $signalVal -ge 50) {
        "pass"
    } elseif ($state -eq "connected" -and $signalVal -lt 50) {
        "warning"
    } else {
        "pass"
    }

    $summaryText = if ($state -eq "connected") {
        "Connected to '$ssid' ($signalVal% signal, Channel $channel, Radio $radio, Gateway Latency: $gwLatency)."
    } else {
        "Wireless interface '$name' is present but in state '$state'."
    }

    $payload = @{
        status  = $statusOutcome
        summary = $summaryText
        data    = @($results)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query Wi-Fi diagnostics: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
