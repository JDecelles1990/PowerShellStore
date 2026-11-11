<#
.SYNOPSIS
    Measures network connection quality, latency, packet loss, and jitter against key network gateways or remote hosts.
.PSSTORE_META
    {
        "title": "Test Network Quality & Jitter",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 45,
        "output_mode": "json",
        "params": [
            {"name": "TargetHost", "type": "string", "default": "1.1.1.1"},
            {"name": "PingCount", "type": "int", "default": 10, "min": 4, "max": 50},
            {"name": "MaxAcceptableLatencyMs", "type": "int", "default": 100, "min": 10, "max": 1000}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetHost = "1.1.1.1",

    [Parameter(Mandatory = $false)]
    [int]$PingCount = 10,

    [Parameter(Mandatory = $false)]
    [int]$MaxAcceptableLatencyMs = 100
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$qualityRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

$rttList = [System.Collections.Generic.List[double]]::new()
$lostCount = 0

try {
    # Resolve Hostname
    $ipAddress = $TargetHost
    try {
        $resolved = [System.Net.Dns]::GetHostAddresses($TargetHost)
        if ($resolved -and $resolved.Count -gt 0) {
            $ipAddress = $resolved[0].IPAddressToString
        }
    } catch {
        # Proceed with literal host
    }

    # Execute burst testing with ICMP or TCP fallback
    $icmpAvailable = $true
    for ($i = 1; $i -le $PingCount; $i++) {
        $rtt = -1.0

        if ($icmpAvailable) {
            try {
                $pinger = New-Object System.Net.NetworkInformation.Ping
                $reply = $pinger.Send($ipAddress, 1500)
                if ($reply.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                    $rtt = [double]$reply.RoundtripTime
                } else {
                    $lostCount++
                }
            }
            catch {
                # ICMP blocked or unauthorized; switch to TCP Socket fallback on port 443/80
                $icmpAvailable = $false
            }
        }

        if (-not $icmpAvailable) {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $tcp = New-Object System.Net.Sockets.TcpClient
            try {
                $ar = $tcp.BeginConnect($ipAddress, 443, $null, $null)
                $connected = $ar.AsyncWaitHandle.WaitOne(1500, $false)
                $sw.Stop()
                if ($connected) {
                    $rtt = [double]$sw.ElapsedMilliseconds
                } else {
                    $lostCount++
                }
            }
            catch {
                $lostCount++
            }
            finally {
                $tcp.Close()
            }
        }

        if ($rtt -ge 0) {
            $rttList.Add($rtt)
        }
        Start-Sleep -Milliseconds 100
    }

    $received = $rttList.Count
    $sent = $PingCount
    $lossPct = [math]::Round((($sent - $received) / $sent) * 100.0, 1)

    $minLatency = 0.0
    $maxLatency = 0.0
    $avgLatency = 0.0
    $jitter = 0.0

    if ($received -gt 0) {
        $minLatency = ($rttList | Measure-Object -Minimum).Minimum
        $maxLatency = ($rttList | Measure-Object -Maximum).Maximum
        $avgLatency = [math]::Round(($rttList | Measure-Object -Average).Average, 1)

        # Calculate Jitter (Mean Absolute Successive Difference)
        if ($received -gt 1) {
            $diffSum = 0.0
            for ($k = 0; $k -lt ($received - 1); $k++) {
                $diffSum += [math]::Abs($rttList[$k + 1] - $rttList[$k])
            }
            $jitter = [math]::Round(($diffSum / ($received - 1)), 1)
        }
    }

    # Evaluate Quality State
    $qualityRating = "Excellent"
    if ($lossPct -gt 10.0 -or $avgLatency -gt ($MaxAcceptableLatencyMs * 2)) {
        $status = "fail"
        $qualityRating = "Poor (Severe Packet Loss or Latency)"
        $summary = "Critical: High packet loss ($lossPct%) or severe latency (${avgLatency} ms) to $TargetHost."
    }
    elseif ($lossPct -gt 0.0 -or $avgLatency -gt $MaxAcceptableLatencyMs -or $jitter -gt 30.0) {
        $status = "warning"
        $qualityRating = "Fair / Degraded"
        $summary = "Warning: Elevated latency (${avgLatency} ms), packet loss (${lossPct}%), or jitter (${jitter} ms)."
    }
    else {
        $status = "pass"
        $qualityRating = "Good / Stable"
        $summary = "Network connection to $TargetHost is healthy. Avg: ${avgLatency} ms | Jitter: ${jitter} ms | Loss: ${lossPct}%."
    }

    $metricMethod = if ($icmpAvailable) { "ICMP Ping" } else { "TCP Connect (Port 443)" }

    $qualityRecords.Add([PSCustomObject]@{
        TargetHost        = $TargetHost
        ResolvedIP        = $ipAddress
        PacketsSent       = $sent
        PacketsReceived   = $received
        PacketLossPercent = "$lossPct%"
        MinLatencyMs      = "$minLatency ms"
        MaxLatencyMs      = "$maxLatency ms"
        AvgLatencyMs      = "$avgLatency ms"
        JitterMs          = "$jitter ms"
        Method            = $metricMethod
        QualityRating     = $qualityRating
    })

    # Human-Readable ASCII Table Output
    $displayTable = @(
        [PSCustomObject]@{ Metric = "Target Host"; Value = "$TargetHost ($ipAddress)" },
        [PSCustomObject]@{ Metric = "Probe Method"; Value = $metricMethod },
        [PSCustomObject]@{ Metric = "Packets (Sent / Recv)"; Value = "$sent / $received" },
        [PSCustomObject]@{ Metric = "Packet Loss"; Value = "$lossPct%" },
        [PSCustomObject]@{ Metric = "Latency (Min / Avg / Max)"; Value = "$minLatency ms / $avgLatency ms / $maxLatency ms" },
        [PSCustomObject]@{ Metric = "Jitter"; Value = "$jitter ms" },
        [PSCustomObject]@{ Metric = "Overall Quality"; Value = $qualityRating }
    )
    $tableOutput = $displayTable | Format-Table -AutoSize | Out-String
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Network quality test failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($qualityRecords)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
