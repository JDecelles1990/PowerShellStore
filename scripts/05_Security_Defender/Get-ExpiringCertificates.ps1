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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $DaysThreshold = [math]::Max(1, [math]::Min(180, $DaysThreshold))
    $now = Get-Date
    $warnDate = $now.AddDays($DaysThreshold)

    $stores = @(
        @{ Path = "Cert:\CurrentUser\My"; Name = "CurrentUser\Personal" },
        @{ Path = "Cert:\LocalMachine\My"; Name = "LocalMachine\Personal" },
        @{ Path = "Cert:\LocalMachine\Root"; Name = "LocalMachine\Root" }
    )

    foreach ($store in $stores) {
        try {
            if (Test-Path -Path $store.Path -ErrorAction Stop) {
                $certs = Get-ChildItem -Path $store.Path -ErrorAction Stop
                foreach ($cert in $certs) {
                    if ($null -eq $cert.NotAfter) { continue }
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

                        $results.Add([PSCustomObject]@{
                            Store         = $store.Name
                            Subject       = $cleanSubject
                            Issuer        = $cleanIssuer
                            Expiration    = $cert.NotAfter.ToString("yyyy-MM-dd")
                            DaysRemaining = $diffDays
                            Status        = if ($isExpired) { "EXPIRED" } else { "EXPIRING SOON" }
                            Thumbprint    = $cert.Thumbprint
                        })
                    }
                }
            }
        }
        catch {
            $errors.Add("Certificate store notice ($($store.Name)): $($_.Exception.Message)")
        }
    }

    if ($results.Count -eq 0) {
        $status = "pass"
        $summary = "All certificates valid: 0 certificates expiring within the next $DaysThreshold day(s)."
        Write-Output "No expired or expiring certificates found within the $DaysThreshold-day threshold."
    }
    else {
        # Human-readable table first
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""

        $status = "warning"
        $summary = "Found $($results.Count) certificate(s) that are expired or expiring within $DaysThreshold day(s)."
    }
}
catch {
    $status = "error"
    $summary = "Failed to audit certificate stores: $($_.Exception.Message)"
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
