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

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $arch = $env:PROCESSOR_ARCHITECTURE
    try {
        $cimArch = (Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop).OSArchitecture
        if ($cimArch) { $arch = $cimArch }
    }
    catch {
        # Fallback to environment variable
    }

    $envInfo = [PSCustomObject]@{
        EchoMessage    = $Message
        ComputerName   = $env:COMPUTERNAME
        UserName       = $env:USERNAME
        OSArchitecture = $arch
        Timestamp      = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    $results.Add($envInfo)

    # Human-readable table before JSON envelope
    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""

    $summary = "Custom diagnostic executed successfully: $Message"
}
catch {
    $status = "error"
    $summary = "Custom diagnostic failed: $($_.Exception.Message)"
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
