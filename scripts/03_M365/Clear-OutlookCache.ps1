<#
.SYNOPSIS
    Clears Microsoft Outlook temporary files, attachment cache, RoamCache, Forms cache, and Offline Address Books to resolve launch crashes, sync errors, and attachment lockups.
.PSSTORE_META
    {
        "title": "Clear Microsoft Outlook Cache",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 60,
        "output_mode": "json",
        "params": [
            {"name": "CloseOutlook", "type": "bool", "default": true},
            {"name": "ClearAttachmentTemp", "type": "bool", "default": true},
            {"name": "ClearRoamCache", "type": "bool", "default": true},
            {"name": "PreserveAutoComplete", "type": "bool", "default": true},
            {"name": "ClearOfflineAddressBook", "type": "bool", "default": true},
            {"name": "ClearFormsCache", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$CloseOutlook = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearAttachmentTemp = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearRoamCache = $true,

    [Parameter(Mandatory = $false)]
    [bool]$PreserveAutoComplete = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearOfflineAddressBook = $true,

    [Parameter(Mandatory = $false)]
    [bool]$ClearFormsCache = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = "Outlook cache cleanup completed successfully."
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$actions = [System.Collections.Generic.List[string]]::new()

$totalFilesDeleted = 0
$totalBytesFreed = [long]0

function Test-DirSafe {
    param ([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        return [System.IO.Directory]::Exists($Path)
    } catch {
        return $false
    }
}

function Remove-FileSafe {
    param (
        [string]$FilePath,
        [ref]$FilesCounter,
        [ref]$BytesCounter
    )
    try {
        if ([System.IO.File]::Exists($FilePath)) {
            $fi = [System.IO.FileInfo]::new($FilePath)
            $len = [long]$fi.Length
            [System.IO.File]::Delete($FilePath)
            $FilesCounter.Value++
            $BytesCounter.Value += $len
        }
    }
    catch {
        # File may be locked by another application or in-use; skip silently
    }
}

try {
    # 1. Close or Terminate Running Outlook Processes
    $outlookClosed = $false
    if ($CloseOutlook) {
        $processes = Get-Process -Name "OUTLOOK", "olk" -ErrorAction SilentlyContinue
        if ($processes) {
            foreach ($proc in $processes) {
                try {
                    $proc.CloseMainWindow() | Out-Null
                } catch {}
            }
            Start-Sleep -Seconds 2

            $remaining = Get-Process -Name "OUTLOOK", "olk" -ErrorAction SilentlyContinue
            if ($remaining) {
                foreach ($proc in $remaining) {
                    try {
                        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                    } catch {}
                }
            }
            $outlookClosed = $true
            $actions.Add("Terminated active Outlook and New Outlook processes.")
        } else {
            $actions.Add("No running Outlook processes detected.")
        }
    }

    # 2. Clear Outlook Secure Temp (Attachment Cache / Content.Outlook)
    $attachmentTempCleared = $false
    if ($ClearAttachmentTemp) {
        $candidatePaths = [System.Collections.Generic.List[string]]::new()

        # Check Office Registry keys (Read-Only via .NET to prevent SecurityException)
        $officeVersions = @("16.0", "15.0", "14.0")
        foreach ($ver in $officeVersions) {
            try {
                $subKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Microsoft\Office\$ver\Outlook\Security", $false)
                if ($subKey) {
                    $regVal = $subKey.GetValue("OutlookSecureTempFolder")
                    $subKey.Close()
                    if ($regVal -and (Test-DirSafe -Path $regVal)) {
                        $candidatePaths.Add($regVal)
                    }
                }
            } catch {}
        }

        # Check default Content.Outlook paths
        $defaultOlk1 = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\Windows\INetCache\Content.Outlook"
        $defaultOlk2 = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\Windows\Temporary Internet Files\Content.Outlook"
        if (Test-DirSafe -Path $defaultOlk1) { $candidatePaths.Add($defaultOlk1) }
        if (Test-DirSafe -Path $defaultOlk2) { $candidatePaths.Add($defaultOlk2) }

        $cleanedOlk = 0
        foreach ($targetDir in ($candidatePaths | Select-Object -Unique)) {
            try {
                $files = [System.IO.Directory]::GetFiles($targetDir, "*.*", [System.IO.SearchOption]::AllDirectories)
                foreach ($f in $files) {
                    Remove-FileSafe -FilePath $f -FilesCounter ([ref]$totalFilesDeleted) -BytesCounter ([ref]$totalBytesFreed)
                    $cleanedOlk++
                }
            } catch {}
        }
        $attachmentTempCleared = $true
        $actions.Add("Purged $cleanedOlk attachment cache files from Secure Temp.")
    }

    # 3. Clear RoamCache
    $roamCacheCleared = $false
    $roamCachePath = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\Outlook\RoamCache"
    if ($ClearRoamCache -and (Test-DirSafe -Path $roamCachePath)) {
        $roamCount = 0
        try {
            $files = [System.IO.Directory]::GetFiles($roamCachePath, "*.*", [System.IO.SearchOption]::TopDirectoryOnly)
            foreach ($f in $files) {
                $fName = [System.IO.Path]::GetFileName($f)
                if ($PreserveAutoComplete -and ($fName -like "Stream_Autocomplete*.dat")) {
                    continue
                }
                Remove-FileSafe -FilePath $f -FilesCounter ([ref]$totalFilesDeleted) -BytesCounter ([ref]$totalBytesFreed)
                $roamCount++
            }
        } catch {}
        $roamCacheCleared = $true
        $note = if ($PreserveAutoComplete) { " (auto-complete preserved)" } else { " (including auto-complete)" }
        $actions.Add("Purged $roamCount stream cache files from RoamCache$note.")
    }

    # 4. Clear Offline Address Book (.oab) files
    $oabCleared = $false
    $oabRoot = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\Outlook\Offline Address Books"
    if ($ClearOfflineAddressBook -and (Test-DirSafe -Path $oabRoot)) {
        $oabCount = 0
        try {
            $files = [System.IO.Directory]::GetFiles($oabRoot, "*.*", [System.IO.SearchOption]::AllDirectories)
            foreach ($f in $files) {
                Remove-FileSafe -FilePath $f -FilesCounter ([ref]$totalFilesDeleted) -BytesCounter ([ref]$totalBytesFreed)
                $oabCount++
            }
        } catch {}
        $oabCleared = $true
        $actions.Add("Purged $oabCount Offline Address Book (.oab) files.")
    }

    # 5. Clear Forms Cache (FRMCACHE.DAT)
    $formsCleared = $false
    $formsDir = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Microsoft\FORMS"
    if ($ClearFormsCache -and (Test-DirSafe -Path $formsDir)) {
        $fCount = 0
        try {
            $files = [System.IO.Directory]::GetFiles($formsDir, "*.*", [System.IO.SearchOption]::TopDirectoryOnly)
            foreach ($f in $files) {
                Remove-FileSafe -FilePath $f -FilesCounter ([ref]$totalFilesDeleted) -BytesCounter ([ref]$totalBytesFreed)
                $fCount++
            }
        } catch {}
        $formsCleared = $true
        $actions.Add("Purged $fCount forms cache file(s) from Microsoft\\FORMS.")
    }

    # 6. Check New Outlook for Windows (OLK) LocalCache
    $newOutlookRoot = Join-Path -Path $env:LOCALAPPDATA -ChildPath "Packages\Microsoft.OutlookForWindows_8wekyb3d8bbwe\LocalCache"
    if (Test-DirSafe -Path $newOutlookRoot) {
        $oldCount = 0
        try {
            $files = [System.IO.Directory]::GetFiles($newOutlookRoot, "*.*", [System.IO.SearchOption]::AllDirectories)
            foreach ($f in $files) {
                Remove-FileSafe -FilePath $f -FilesCounter ([ref]$totalFilesDeleted) -BytesCounter ([ref]$totalBytesFreed)
                $oldCount++
            }
            $actions.Add("Purged $oldCount cached items from New Outlook LocalCache.")
        } catch {}
    }

    $freedMB = [math]::Round([double]$totalBytesFreed / 1MB, 2)
    $summary = "Outlook cleanup completed. Removed $totalFilesDeleted file(s), freed ${freedMB} MB."

    $results.Add([PSCustomObject]@{
        OutlookClosed             = $outlookClosed
        AttachmentTempCleared     = $attachmentTempCleared
        RoamCacheCleared          = $roamCacheCleared
        AutoCompletePreserved     = $PreserveAutoComplete
        OfflineAddressBookCleared = $oabCleared
        FormsCacheCleared         = $formsCleared
        TotalFilesDeleted         = $totalFilesDeleted
        MegabytesFreed            = $freedMB
        ActionsLog                = ($actions -join " | ")
    })
}
catch {
    $status = "error"
    $summary = "Outlook cache cleanup failed: $($_.Exception.Message)"
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
