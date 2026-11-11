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

try {
    $adapters = Get-NetAdapter -Name $AdapterName -ErrorAction Stop |
        Where-Object { $_.Status -eq 'Up' } |
        ForEach-Object {
            $dns = Get-DnsClientServerAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction Stop
            [PSCustomObject]@{
                Name       = $_.Name
                Status     = [string]$_.Status
                MacAddress = $_.MacAddress
                LinkSpeed  = $_.LinkSpeed
                DNSServers = ($dns.ServerAddresses -join ", ")
            }
        }

    $payload = @{
        status  = "pass"
        summary = "Found $(@($adapters).Count) active adapter(s)."
        data    = @($adapters)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Network snapshot failed: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
