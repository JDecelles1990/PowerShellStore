<#
.SYNOPSIS
    Audits Local Machine and Current User certificate stores for expired or soon-to-expire certificates.
.PSSTORE_META
    {
        "title": "Get Expiring & Expired Certificates",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "DaysThreshold", "type": "int", "default": 30, "min": 1, "max": 180}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$DaysThreshold = 30
)

$ErrorActionPreference = 'Stop'

try {
    $now = Get-Date
    $warnDate = $now.AddDays($DaysThreshold)

    $stores = @(
        @{ Path = "Cert:\CurrentUser\My"; Name = "CurrentUser\Personal" },
        @{ Path = "Cert:\LocalMachine\My"; Name = "LocalMachine\Personal" },
        @{ Path = "Cert:\LocalMachine\Root"; Name = "LocalMachine\Root" }
    )

    $results = @()
    foreach ($store in $stores) {
        if (Test-Path $store.Path) {
            $certs = Get-ChildItem -Path $store.Path -ErrorAction SilentlyContinue
            foreach ($cert in $certs) {
                if ($cert.NotAfter -le $warnDate) {
                    $isExpired = $cert.NotAfter -lt $now
                    $diffDays = [int]($cert.NotAfter - $now).TotalDays

                    $cleanSubject = if ($cert.Subject) {
                        ($cert.Subject -replace 'CN=', '').Split(',')[0].Trim()
                    } else {
                        "Unknown Subject"
                    }

                    $cleanIssuer = if ($cert.Issuer) {
                        ($cert.Issuer -replace 'CN=', '').Split(',')[0].Trim()
                    } else {
                        "Unknown Issuer"
                    }

                    $results += [PSCustomObject]@{
                        Store         = $store.Name
                        Subject       = $cleanSubject
                        Issuer        = $cleanIssuer
                        Expiration    = $cert.NotAfter.ToString("yyyy-MM-dd")
                        DaysRemaining = $diffDays
                        Status        = if ($isExpired) { "EXPIRED" } else { "EXPIRING SOON" }
                        Thumbprint    = $cert.Thumbprint
                    }
                }
            }
        }
    }

    if ($results.Count -eq 0) {
        Write-Output "No expired or expiring certificates found within the $DaysThreshold-day threshold."
        $payload = @{
            status  = "pass"
            summary = "All certificates valid: 0 certificates expiring within the next $DaysThreshold day(s)."
            data    = @()
            errors  = @()
        }
    }
    else {
        # Human-readable table first
        $results | Format-Table -AutoSize | Out-String | Write-Output

        $payload = @{
            status  = "warning"
            summary = "Found $($results.Count) certificate(s) that are expired or expiring within $DaysThreshold day(s)."
            data    = @($results)
            errors  = @()
        }
    }

    $payload | ConvertTo-Json -Depth 4 -Compress
}
catch {
    $errPayload = @{
        status  = "error"
        summary = "Failed to audit certificate stores: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
    $errPayload | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

