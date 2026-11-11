<#
.SYNOPSIS
    Maps active TCP and UDP listening ports to their local processes and executable paths.
.PSSTORE_META
    {
        "title": "Get Active Listening Ports",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "Protocol", "type": "string", "default": "All"},
            {"name": "PortFilter", "type": "int", "default": 0, "min": 0, "max": 65535}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Protocol = "All",

    [Parameter(Mandatory = $false)]
    [int]$PortFilter = 0
)

$ErrorActionPreference = 'Stop'

try {
    # Validate Protocol
    if ($Protocol -notmatch '^(All|TCP|UDP)$') {
        $Protocol = "All"
    }

    # Pre-cache process map for fast lookup
    $processMap = @{}
    Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
        $processMap[$_.Id] = @{
            Name = $_.ProcessName
            Path = try { $_.Path } catch { "System/Protected" }
        }
    }

    $rawEntries = @()

    # 1. Gather TCP Listeners
    if ($Protocol -in @("All", "TCP")) {
        $tcpListeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
        if ($tcpListeners) {
            foreach ($tcp in $tcpListeners) {
                if ($PortFilter -eq 0 -or $tcp.LocalPort -eq $PortFilter) {
                    $pInfo = $processMap[[int]$tcp.OwningProcess]
                    $rawEntries += [PSCustomObject]@{
                        Protocol     = "TCP"
                        LocalAddress = [string]$tcp.LocalAddress
                        LocalPort    = [int]$tcp.LocalPort
                        PID          = [int]$tcp.OwningProcess
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    }
                }
            }
        }
    }

    # 2. Gather UDP Endpoints
    if ($Protocol -in @("All", "UDP")) {
        $udpListeners = Get-NetUDPEndpoint -ErrorAction SilentlyContinue
        if ($udpListeners) {
            foreach ($udp in $udpListeners) {
                if ($PortFilter -eq 0 -or $udp.LocalPort -eq $PortFilter) {
                    $pInfo = $processMap[[int]$udp.OwningProcess]
                    $rawEntries += [PSCustomObject]@{
                        Protocol     = "UDP"
                        LocalAddress = [string]$udp.LocalAddress
                        LocalPort    = [int]$udp.LocalPort
                        PID          = [int]$udp.OwningProcess
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    }
                }
            }
        }
    }

    $sortedEntries = @($rawEntries | Sort-Object LocalPort)

    # Human-readable table first
    if ($sortedEntries.Count -gt 0) {
        $sortedEntries | Format-Table -AutoSize | Out-String | Write-Output
    }
    else {
        Write-Output "No active listening ports matched the filter (Protocol: $Protocol, Port: $PortFilter)."
    }

    $payload = @{
        status  = "pass"
        summary = "Discovered $($sortedEntries.Count) active listening port(s) [Protocol: $Protocol]."
        data    = @($sortedEntries)
        errors  = @()
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to query listening ports: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

