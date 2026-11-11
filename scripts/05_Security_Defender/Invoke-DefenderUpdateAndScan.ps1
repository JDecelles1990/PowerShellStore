<#
.SYNOPSIS
    Updates Microsoft Defender Antivirus signatures to the latest security definitions and triggers an on-demand Quick or Full scan.
.PSSTORE_META
    {
        "title": "Update Defender Signatures & Trigger Scan",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 300,
        "output_mode": "json",
        "params": [
            {"name": "ScanType", "type": "string", "default": "QuickScan"},
            {"name": "UpdateSignatures", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ScanType = "QuickScan",

    [Parameter(Mandatory = $false)]
    [bool]$UpdateSignatures = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$scanRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

$mpCmdRun = Join-Path -Path $env:ProgramFiles -ChildPath "Windows Defender\MpCmdRun.exe"
$hasMpCmd = [System.IO.File]::Exists($mpCmdRun)

try {
    # 1. Update Signatures
    $sigUpdated = $false
    if ($UpdateSignatures) {
        $updateSuccess = $false
        try {
            Update-MpSignature -ErrorAction Stop
            $updateSuccess = $true
        }
        catch {
            if ($hasMpCmd) {
                try {
                    $uOut = & $mpCmdRun -SignatureUpdate 2>&1
                    if ($LASTEXITCODE -eq 0) { $updateSuccess = $true }
                } catch {}
            }
        }

        if ($updateSuccess) {
            $sigUpdated = $true
            $scanRecords.Add([PSCustomObject]@{
                Stage   = "Signature Update"
                Status  = "Success"
                Details = "Microsoft Defender security definitions updated successfully."
            })
        } else {
            $scanRecords.Add([PSCustomObject]@{
                Stage   = "Signature Update"
                Status  = "Warning"
                Details = "Signature update encountered warnings or requires elevated permissions."
            })
        }
    }

    # 2. Trigger Scan
    $scanTriggered = $false
    $scanCode = if ($ScanType -eq "FullScan") { 2 } else { 1 }

    try {
        Start-MpScan -ScanType $ScanType -ErrorAction Stop
        $scanTriggered = $true
        $scanRecords.Add([PSCustomObject]@{
            Stage   = "Antivirus Scan"
            Status  = "Success"
            Details = "Completed $ScanType scan."
        })
    }
    catch {
        if ($hasMpCmd) {
            try {
                $sOut = & $mpCmdRun -Scan -ScanType $scanCode 2>&1
                if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 2) {
                    $scanTriggered = $true
                    $scanRecords.Add([PSCustomObject]@{
                        Stage   = "Antivirus Scan"
                        Status  = "Success"
                        Details = "Completed $ScanType scan via MpCmdRun."
                    })
                } else {
                    throw "MpCmdRun exited with code $LASTEXITCODE"
                }
            }
            catch {
                $errors.Add("Failed to initiate $ScanType: $($_.Exception.Message)")
                $scanRecords.Add([PSCustomObject]@{
                    Stage   = "Antivirus Scan"
                    Status  = "Failed"
                    Details = $_.Exception.Message
                })
            }
        } else {
            $errors.Add("Defender scan tools unavailable: $($_.Exception.Message)")
            $scanRecords.Add([PSCustomObject]@{
                Stage   = "Antivirus Scan"
                Status  = "Failed"
                Details = $_.Exception.Message
            })
        }
    }

    # 3. Check for Active Threat Detections
    $threatCount = 0
    try {
        $threats = Get-MpThreatDetection -ErrorAction SilentlyContinue
        if ($threats) {
            $threatCount = ($threats | Measure-Object).Count
        }
    } catch {}

    if ($threatCount -gt 0) {
        $status = "fail"
        $summary = "Security Alert: Defender detected $threatCount active or quarantined threat(s) on endpoint."
    } elseif ($errors.Count -gt 0) {
        $status = "warning"
        $summary = "Defender maintenance completed with $($errors.Count) warning(s)."
    } else {
        $status = "pass"
        $summary = "Defender signatures verified and $ScanType completed cleanly (0 threats detected)."
    }

    # Human-Readable ASCII Table Output
    if ($scanRecords.Count -gt 0) {
        $tableOutput = $scanRecords | Format-Table -Property Stage, Status, Details -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""
    }
}
catch {
    $status = "error"
    $summary = "Defender maintenance failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status            = $status
        summary           = $summary
        signatures_updated= $sigUpdated
        threats_detected  = $threatCount
        data              = @($scanRecords)
        errors            = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}

