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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $Port = [math]::Max(1, [math]::Min(65535, $Port))
    $TimeoutMs = [math]::Max(500, [math]::Min(15000, $TimeoutMs))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connected = $false

    try {
        $asyncResult = $tcpClient.BeginConnect($TargetHost, $Port, $null, $null)
        $success = $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        $stopwatch.Stop()

        if ($success -and $tcpClient.Connected) {
            $tcpClient.EndConnect($asyncResult)
            $connected = $true
        }
    }
    finally {
        $tcpClient.Close()
    }

    $status = if ($connected) { "pass" } else { "fail" }
    $summary = if ($connected) {
        "Connected to ${TargetHost}:${Port} successfully in $($stopwatch.ElapsedMilliseconds) ms."
    } else {
        "Connection to ${TargetHost}:${Port} timed out or was refused after $($stopwatch.ElapsedMilliseconds) ms."
    }

    $results.Add([PSCustomObject]@{
        TargetHost        = $TargetHost
        Port              = $Port
        Connected         = $connected
        ResponseTimeMs    = $stopwatch.ElapsedMilliseconds
        TimeoutConfigured = $TimeoutMs
    })

    if (-not $connected) {
        $errors.Add("Port $Port unreachable on $TargetHost")
    }

    # Human-readable table before JSON envelope
    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""
}
catch {
    $status = "error"
    $summary = "Port test encountered an error: $($_.Exception.Message)"
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
