<#
.SYNOPSIS
    Starter template for technician-authored custom diagnostics and ad-hoc troubleshooting scripts.
.PSSTORE_META
    {
        "title": "Sample Custom Diagnostic",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": [
            {"name": "Message", "type": "string", "default": "Hello from PowerShellStore"}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Message = "Hello from PowerShellStore"
)

$ErrorActionPreference = 'Stop'

try {
    $arch = $env:PROCESSOR_ARCHITECTURE
    try {
        $cimArch = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).OSArchitecture
        if ($cimArch) { $arch = $cimArch }
    } catch {
        # Fallback to environment variable
    }

    $envInfo = [PSCustomObject]@{
        EchoMessage    = $Message
        ComputerName   = $env:COMPUTERNAME
        UserName       = $env:USERNAME
        OSArchitecture = $arch
        Timestamp      = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }

    $payload = @{
        status  = "pass"
        summary = "Custom diagnostic executed successfully: $Message"
        data    = @($envInfo)
        errors  = @()
    }
}
catch {
    $payload = @{
        status  = "error"
        summary = "Custom diagnostic failed: $($_.Exception.Message)"
        data    = @()
        errors  = @($_.Exception.Message)
    }
}
finally {
    $payload | ConvertTo-Json -Depth 4 -Compress
}
