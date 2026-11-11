<#
.SYNOPSIS
    Queries endpoint Microsoft Entra ID (Azure AD) join status and device identity for M365 diagnostics.
.PSSTORE_META
    {
        "title": "Get Entra ID Join & Device Status",
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
    $dsregOutput = & dsregcmd.exe /status 2>&1
    
    $azureAdJoined = "NO"
    $enterpriseJoined = "NO"
    $domainJoined = "NO"
    $tenantName = "N/A"
    $deviceId = "N/A"

    foreach ($line in $dsregOutput) {
        $trimmed = $line.ToString().Trim()
        if ($trimmed -match "^AzureAdJoined\s*:\s*(.+)$") {
            $azureAdJoined = $matches[1].Trim()
        } elseif ($trimmed -match "^EnterpriseJoined\s*:\s*(.+)$") {
            $enterpriseJoined = $matches[1].Trim()
        } elseif ($trimmed -match "^DomainJoined\s*:\s*(.+)$") {
            $domainJoined = $matches[1].Trim()
        } elseif ($trimmed -match "^TenantName\s*:\s*(.+)$") {
            $tenantName = $matches[1].Trim()
        } elseif ($trimmed -match "^DeviceId\s*:\s*(.+)$") {
            $deviceId = $matches[1].Trim()
        }
    }

    $isJoined = ($azureAdJoined -eq "YES") -or ($domainJoined -eq "YES")

    $status = if ($isJoined) { "pass" } else { "warning" }
    $summary = if ($azureAdJoined -eq "YES") {
        "Endpoint is Entra ID (Azure AD) Joined to tenant: $tenantName"
    } elseif ($domainJoined -eq "YES") {
        "Endpoint is Active Directory Domain Joined (Hybrid or On-Prem)."
    } else {
        "Endpoint is NOT joined to Entra ID or Active Directory (Workgroup)."
    }

    $details = [PSCustomObject]@{
        AzureAdJoined    = $azureAdJoined
        DomainJoined     = $domainJoined
        EnterpriseJoined = $enterpriseJoined
        TenantName       = $tenantName
        DeviceId         = $deviceId
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
        summary = "Failed to query Entra ID registration status: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}

