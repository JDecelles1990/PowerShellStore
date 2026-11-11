<#
.SYNOPSIS
    Reports Microsoft Defender antivirus status, real-time protection, and signature update versions.
.PSSTORE_META
    {
        "title": "Get Microsoft Defender Status",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": []
    }
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

try {
    $mp = Get-MpComputerStatus -ErrorAction Stop

    $daysSinceUpdate = if ($mp.AntivirusSignatureLastUpdated) {
        [math]::Round(((Get-Date) - $mp.AntivirusSignatureLastUpdated).TotalDays, 1)
    } else {
        999
    }

    $isHealthy = $mp.AntivirusEnabled -and $mp.RealTimeProtectionEnabled -and ($daysSinceUpdate -lt 5)

    $status = if ($isHealthy) { "pass" } else { "warning" }
    $summary = if ($isHealthy) {
        "Microsoft Defender is active, Real-Time Protection is ENABLED, and signatures are current (${daysSinceUpdate} days old)."
    } else {
        "Defender attention needed: Enabled=$($mp.AntivirusEnabled), RTP=$($mp.RealTimeProtectionEnabled), SigAge=${daysSinceUpdate}d."
    }

    $details = [PSCustomObject]@{
        AntivirusEnabled           = [bool]$mp.AntivirusEnabled
        RealTimeProtectionEnabled  = [bool]$mp.RealTimeProtectionEnabled
        AntispywareEnabled         = [bool]$mp.AntispywareEnabled
        AntivirusSignatureVersion  = [string]$mp.AntivirusSignatureVersion
        EngineVersion              = [string]$mp.AMEngineVersion
        SignatureLastUpdated       = [string]$mp.AntivirusSignatureLastUpdated
        SignatureAgeDays           = $daysSinceUpdate
    }

    $payload = @{
        status  = $status
        summary = $summary
        data    = @($details)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Failed to query Microsoft Defender status: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}

