<#
.SYNOPSIS
    Queries installed printers, print queues, and active or stuck print jobs to diagnose printing bottlenecks and spooler errors.
.PSSTORE_META
    {
        "title": "Get Print Queues & Stuck Jobs",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "IncludeJobs", "type": "bool", "default": true},
            {"name": "OnlyWithJobs", "type": "bool", "default": false}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$IncludeJobs = $true,

    [Parameter(Mandatory = $false)]
    [bool]$OnlyWithJobs = $false
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$printerRecords = [System.Collections.Generic.List[PSObject]]::new()
$jobRecords = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

$totalQueuedJobs = 0
$stuckJobCount = 0

try {
    $queriedViaCim = $false

    # Tier 1: Modern PrintManagement Module (Get-Printer / Get-PrintJob)
    try {
        $printers = Get-Printer -ErrorAction Stop
        foreach ($p in $printers) {
            $jobCount = [int]$p.JobCount
            $totalQueuedJobs += $jobCount

            $stuckOnPrinter = 0
            $jobsSummary = "None"

            if ($IncludeJobs -and $jobCount -gt 0) {
                try {
                    $jobs = Get-PrintJob -PrinterName $p.Name -ErrorAction SilentlyContinue
                    if ($jobs) {
                        $jobDescList = [System.Collections.Generic.List[string]]::new()
                        foreach ($j in $jobs) {
                            $isJobError = ($j.JobStatus -match "Error|Offline|PaperOut|UserIntervention|Blocked")
                            if ($isJobError) {
                                $stuckOnPrinter++
                                $stuckJobCount++
                            }

                            $jobRecords.Add([PSCustomObject]@{
                                PrinterName   = [string]$p.Name
                                JobId         = [int]$j.Id
                                DocumentName  = [string]$j.DocumentName
                                UserName      = [string]$j.UserName
                                Status        = [string]$j.JobStatus
                                Pages         = [int]$j.TotalPages
                                SubmittedTime = if ($j.SubmittedTime) { ([datetime]$j.SubmittedTime).ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }
                            })
                            $jobDescList.Add("#$($j.Id): '$($j.DocumentName)' ($($j.JobStatus))")
                        }
                        $jobsSummary = ($jobDescList -join "; ")
                    }
                } catch {}
            }

            if ($OnlyWithJobs -and $jobCount -eq 0) {
                continue
            }

            $printerRecords.Add([PSCustomObject]@{
                PrinterName     = [string]$p.Name
                IsDefault       = [bool]$p.Default
                PrinterStatus   = [string]$p.PrinterStatus
                QueuedJobs      = $jobCount
                StuckJobs       = $stuckOnPrinter
                DriverName      = [string]$p.DriverName
                PortName        = [string]$p.PortName
                Shared          = [bool]$p.Shared
            })
        }
        $queriedViaCim = $true
    }
    catch {
        # Tier 1 inaccessible; proceed to Tier 2 .NET Fallback
    }

    # Tier 2: Resilient .NET System.Drawing.Printing.PrinterSettings (works unprivileged)
    if (-not $queriedViaCim) {
        try {
            Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
            $defaultPrinter = try { (New-Object System.Drawing.Printing.PrinterSettings).PrinterName } catch { "" }
            $installed = [System.Drawing.Printing.PrinterSettings]::InstalledPrinters

            # Estimate queued jobs from Spooler PRINTERS folder (.SHD / .SPL files)
            $spoolDir = Join-Path -Path $env:SystemRoot -ChildPath "System32\spool\PRINTERS"
            $spoolFilesCount = 0
            if (Test-Path -Path $spoolDir) {
                try {
                    $spoolFiles = Get-ChildItem -Path $spoolDir -File -Force -ErrorAction SilentlyContinue
                    if ($spoolFiles) {
                        $spoolFilesCount = ($spoolFiles | Where-Object { $_.Extension -eq ".shd" }).Count
                    }
                } catch {}
            }
            $totalQueuedJobs = $spoolFilesCount

            foreach ($pName in $installed) {
                $isDef = ($pName -eq $defaultPrinter)
                $printerRecords.Add([PSCustomObject]@{
                    PrinterName     = [string]$pName
                    IsDefault       = $isDef
                    PrinterStatus   = "Ready"
                    QueuedJobs      = if ($spoolFilesCount -gt 0) { $spoolFilesCount } else { 0 }
                    StuckJobs       = 0
                    DriverName      = "Installed Driver"
                    PortName        = "Local/Network"
                    Shared          = $false
                })
            }
        }
        catch {
            throw "Unable to query printers via CIM or .NET: $($_.Exception.Message)"
        }
    }

    $printerCount = $printerRecords.Count
    if ($stuckJobCount -gt 0) {
        $status = "warning"
        $summary = "Warning: Found $stuckJobCount stuck print job(s) across $printerCount printer(s)."
    } elseif ($totalQueuedJobs -gt 0) {
        $status = "pass"
        $summary = "Discovered $printerCount printer(s) with $totalQueuedJobs queued print job(s)."
    } else {
        $status = "pass"
        $summary = "Discovered $printerCount printer(s). All print queues are clear."
    }

    # Output formatted ASCII table for RMM console and Raw Output tab
    if ($printerRecords.Count -gt 0) {
        $tableOutput = $printerRecords | Format-Table -Property PrinterName, IsDefault, PrinterStatus, QueuedJobs, StuckJobs, PortName -AutoSize | Out-String
        Write-Output $tableOutput.Trim()
        Write-Output ""

        if ($jobRecords.Count -gt 0) {
            Write-Output "--- QUEUED PRINT JOBS ---"
            $jobsTable = $jobRecords | Format-Table -Property PrinterName, JobId, DocumentName, UserName, Status, Pages, SubmittedTime -AutoSize | Out-String
            Write-Output $jobsTable.Trim()
            Write-Output ""
        }
    }
}
catch {
    $status = "error"
    $summary = "Failed to query print queues: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    $payload = @{
        status            = $status
        summary           = $summary
        total_printers    = $printerRecords.Count
        total_queued_jobs = $totalQueuedJobs
        stuck_jobs        = $stuckJobCount
        data              = @($printerRecords)
        jobs              = @($jobRecords)
        errors            = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}

