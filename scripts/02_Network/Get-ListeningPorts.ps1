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

$status = "pass"
$summary = ""
$sortedEntries = @()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Validate Protocol & PortFilter
    if ($Protocol -notmatch '^(All|TCP|UDP)$') {
        $Protocol = "All"
    }
    $PortFilter = [math]::Max(0, [math]::Min(65535, $PortFilter))

    # Pre-cache process map for fast lookup
    $processMap = @{}
    Get-Process -ErrorAction Stop | ForEach-Object {
        $processMap[$_.Id] = @{
            Name = $_.ProcessName
            Path = try { if ($_.Path) { $_.Path } else { "System/Protected" } } catch { "System/Protected" }
        }
    }

    $rawEntries = [System.Collections.Generic.List[PSObject]]::new()
    $usedCim = $false

    # Tier 1: NetTCPIP Cmdlets
    try {
        if ($Protocol -in @("All", "TCP")) {
            $tcpListeners = Get-NetTCPConnection -State Listen -ErrorAction Stop
            foreach ($tcp in $tcpListeners) {
                if ($PortFilter -eq 0 -or $tcp.LocalPort -eq $PortFilter) {
                    $pInfo = $processMap[[int]$tcp.OwningProcess]
                    $rawEntries.Add([PSCustomObject]@{
                        Protocol     = "TCP"
                        LocalAddress = [string]$tcp.LocalAddress
                        LocalPort    = [int]$tcp.LocalPort
                        PID          = [int]$tcp.OwningProcess
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    })
                }
            }
        }

        if ($Protocol -in @("All", "UDP")) {
            $udpListeners = Get-NetUDPEndpoint -ErrorAction Stop
            foreach ($udp in $udpListeners) {
                if ($PortFilter -eq 0 -or $udp.LocalPort -eq $PortFilter) {
                    $pInfo = $processMap[[int]$udp.OwningProcess]
                    $rawEntries.Add([PSCustomObject]@{
                        Protocol     = "UDP"
                        LocalAddress = [string]$udp.LocalAddress
                        LocalPort    = [int]$udp.LocalPort
                        PID          = [int]$udp.OwningProcess
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    })
                }
            }
        }
        $usedCim = $true
    }
    catch {
        # Tier 1 CIM unavailable; proceed to netstat.exe fallback
        $rawEntries.Clear()
    }

    # Tier 2: Resilient netstat.exe -ano Fallback
    if (-not $usedCim) {
        $netstatLines = & netstat.exe -ano 2>$null
        foreach ($line in $netstatLines) {
            $trimmed = $line.Trim()
            if ($trimmed -match '^(TCP)\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)$') {
                $proto = $Matches[1]
                $addr = $Matches[2].Trim('[]')
                $port = [int]$Matches[3]
                $procId = [int]$Matches[4]
                if (($Protocol -in @("All", "TCP")) -and ($PortFilter -eq 0 -or $port -eq $PortFilter)) {
                    $pInfo = $processMap[$procId]
                    $rawEntries.Add([PSCustomObject]@{
                        Protocol     = $proto
                        LocalAddress = $addr
                        LocalPort    = $port
                        PID          = $procId
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    })
                }
            }
            elseif ($trimmed -match '^(UDP)\s+(\S+):(\d+)\s+\S+\s+(\d+)$') {
                $proto = $Matches[1]
                $addr = $Matches[2].Trim('[]')
                $port = [int]$Matches[3]
                $procId = [int]$Matches[4]
                if (($Protocol -in @("All", "UDP")) -and ($PortFilter -eq 0 -or $port -eq $PortFilter)) {
                    $pInfo = $processMap[$procId]
                    $rawEntries.Add([PSCustomObject]@{
                        Protocol     = $proto
                        LocalAddress = $addr
                        LocalPort    = $port
                        PID          = $procId
                        ProcessName  = if ($pInfo) { $pInfo.Name } else { "Unknown" }
                        ProcessPath  = if ($pInfo -and $pInfo.Path) { $pInfo.Path } else { "N/A" }
                    })
                }
            }
        }
    }

    $sortedEntries = @($rawEntries | Sort-Object -Property LocalPort, Protocol)

    # Human-readable table first
    if ($sortedEntries.Count -gt 0) {
        $tableOutput = $sortedEntries | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No active listening ports matched the filter (Protocol: $Protocol, Port: $PortFilter)."
    }

    $summary = "Discovered $($sortedEntries.Count) active listening port(s) [Protocol: $Protocol]."
}
catch {
    $status = "error"
    $summary = "Failed to query listening ports: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($sortedEntries)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
