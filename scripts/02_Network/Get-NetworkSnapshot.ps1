<#
.SYNOPSIS
    Collects active network adapters and DNS server configurations for RMM or local diagnostics.
.PSSTORE_META
    {
        "title": "Get Network & DNS Snapshot",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "AdapterName", "type": "string", "default": "*"}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$AdapterName = "*"
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$adapters = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $queriedCim = $false

    # Tier 1: Get-NetAdapter & Get-DnsClientServerAddress
    try {
        $netAdapters = Get-NetAdapter -Name $AdapterName -ErrorAction Stop | Where-Object { $_.Status -eq 'Up' }
        foreach ($nic in $netAdapters) {
            $dns = Get-DnsClientServerAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction Stop
            $adapters.Add([PSCustomObject]@{
                Name       = [string]$nic.Name
                Status     = [string]$nic.Status
                MacAddress = [string]$nic.MacAddress
                LinkSpeed  = [string]$nic.LinkSpeed
                DNSServers = ($dns.ServerAddresses -join ", ")
            })
        }
        $queriedCim = $true
    }
    catch {
        # Fallback to .NET NetworkInterface when CIM is unavailable
        $adapters.Clear()
    }

    # Tier 2: Resilient .NET NetworkInterface Fallback
    if (-not $queriedCim) {
        $allNics = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
            Where-Object {
                $_.OperationalStatus -eq 'Up' -and
                $_.NetworkInterfaceType -ne 'Loopback' -and
                ($_.Name -like $AdapterName)
            }
        foreach ($nic in $allNics) {
            $ipProps = $nic.GetIPProperties()
            $dnsAddrs = @($ipProps.DnsAddresses | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | ForEach-Object { $_.IPAddressToString })
            $macBytes = $nic.GetPhysicalAddress().GetAddressBytes()
            $macFormatted = if ($macBytes.Length -gt 0) { ($macBytes | ForEach-Object { $_.ToString("X2") }) -join "-" } else { "N/A" }
            $speedMbps = if ($nic.Speed -gt 0) { "$([math]::Round($nic.Speed / 1000000, 0)) Mbps" } else { "N/A" }

            $adapters.Add([PSCustomObject]@{
                Name       = [string]$nic.Name
                Status     = [string]$nic.OperationalStatus
                MacAddress = $macFormatted
                LinkSpeed  = $speedMbps
                DNSServers = ($dnsAddrs -join ", ")
            })
        }
    }

    # Human-readable table before JSON envelope
    if ($adapters.Count -gt 0) {
        $tableOutput = $adapters | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
    else {
        Write-Output "No active network adapters matched '$AdapterName'."
    }

    $summary = "Found $($adapters.Count) active adapter(s)."
}
catch {
    $status = "error"
    $summary = "Network snapshot failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($adapters)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
