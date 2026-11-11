<#
.SYNOPSIS
    Tests TCP socket connectivity to a target host and port with configurable timeout.
.PSSTORE_META
    {
        "title": "Test TCP Port Connectivity",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": [
            {"name": "TargetHost", "type": "string", "default": "1.1.1.1"},
            {"name": "Port", "type": "int", "default": 443, "min": 1, "max": 65535},
            {"name": "TimeoutMs", "type": "int", "default": 3000, "min": 500, "max": 15000}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetHost = "1.1.1.1",

    [Parameter(Mandatory = $false)]
    [int]$Port = 443,

    [Parameter(Mandatory = $false)]
    [int]$TimeoutMs = 3000
)

$ErrorActionPreference = 'Stop'

try {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $asyncResult = $tcpClient.BeginConnect($TargetHost, $Port, $null, $null)
    $success = $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    $stopwatch.Stop()

    $connected = $false
    if ($success -and $tcpClient.Connected) {
        $tcpClient.EndConnect($asyncResult)
        $connected = $true
    }
    $tcpClient.Close()

    $status = if ($connected) { "pass" } else { "fail" }
    $summary = if ($connected) {
        "Connected to ${TargetHost}:${Port} successfully in $($stopwatch.ElapsedMilliseconds) ms."
    } else {
        "Connection to ${TargetHost}:${Port} timed out or was refused after $($stopwatch.ElapsedMilliseconds) ms."
    }

    $result = [PSCustomObject]@{
        TargetHost        = $TargetHost
        Port              = $Port
        Connected         = $connected
        ResponseTimeMs    = $stopwatch.ElapsedMilliseconds
        TimeoutConfigured = $TimeoutMs
    }

    $errList = if (-not $connected) { @("Port $Port unreachable on $TargetHost") } else { @() }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($result)
        errors  = ,@($errList)
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Port test encountered an error: $($_.Exception.Message)"
        data    = @()
        errors  = ,@($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
