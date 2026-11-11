# PowerShellStore — Antigravity IDE Workspace Instructions (GEMINI.md)

## 1. Project Identity & Core Workflow
`PowerShellStore` is a Windows-focused PySide6 desktop application for IT helpdesk and MSP technicians.
- **Primary Goal (RMM Deployment):** Browse, filter, customize parameters, and copy PowerShell scripts directly to the Windows Clipboard for immediate execution on remote endpoints via an RMM.
- **Secondary Goal (Local Sandbox):** Test and validate scripts locally on the technician's PC using a non-blocking `QProcess` runner before running them in production.
- **File-First Architecture:** All PowerShell scripts live on disk inside categorized subfolders under `scripts/`. Always create and edit real `.ps1` files on disk—never raw SQL blobs—so Python can automatically index them into `data/powershell_store.db`.

---

## 2. Strict Layer Boundaries
Modules must never bypass their architectural layer:

```text
ui/ (PySide6 Presentation)
  ↓
services/ (Scanner, QProcess Runner, Clipboard Injector)
  ↓
repositories/ (SQLite Persistence)
  ↓
data/powershell_store.db + scripts/<Category>/*.ps1
```

1. **`ui/` (Presentation Layer):**
   - Contains PySide6 widgets, views, and layouts only.
   - **FORBIDDEN:** Never import `sqlite3`, `subprocess`, or `hashlib` inside `ui/`. Never run blocking I/O on the GUI thread.
2. **`services/` (Application & Orchestration Layer):**
   - `scanner.py`: Scans `scripts/` subfolders, parses `.PSSTORE_META` JSON headers, computes SHA-256 hashes, and syncs metadata to `catalog_repo.py`.
   - `runner.py`: Validates script paths and SHA-256 checksums, runs scripts non-blockingly via `QProcess` + `QTimer`, and emits Qt Signals.
   - `clipboard_service.py`: Reads `.ps1` files and copies either the **Raw Script** or an **RMM-Ready Script** (with UI parameter values injected into the `param()` block) to the Windows Clipboard.
3. **`repositories/` (Persistence Layer):**
   - `catalog_repo.py`: Owns all SQLite connections, `CREATE TABLE` migrations, and parameterized queries in `data/powershell_store.db`. Always use context managers (`with sqlite3.connect(...)`) for transaction safety.

---

## 3. Script Category Directory Convention
All `.ps1` scripts must be placed in one of the numbered category subfolders inside `scripts/`:
- `scripts/01_System/` — Disk space, uptime, pending reboots, Windows Update, services, processes.
- `scripts/02_Network/` — DNS, DHCP, NIC status, TCP/IP, routing, VPN diagnostics.
- `scripts/03_M365/` — Entra ID (`dsregcmd`), Outlook, Teams, OneDrive, SharePoint cache/sync.
- `scripts/04_Devices/` — Print Spooler resets, printer queues, PnP device/driver checks, driver inventories.
- `scripts/05_Security_Defender/` — Microsoft Defender status, BitLocker, local administrators, firewall.
- `scripts/99_Custom/` — User-created, experimental, or client-specific standalone scripts.

`services/scanner.py` derives the human-readable category name from the parent folder (e.g., `04_Devices` -> `Devices`) unless overridden in `.PSSTORE_META`.

---

## 4. PowerShell Script Contract (`.PSSTORE_META` & Error Handling)
Whenever creating or updating a `.ps1` script in `scripts/`, you **MUST** follow these exact rules:

### 4.1 Mandatory `.PSSTORE_META` Header
Every script must begin with a comment block containing valid JSON under `.PSSTORE_META`:
```powershell
<#
.SYNOPSIS
    Brief one-line description of what the script does.
.PSSTORE_META
    {
        "title": "Human-Readable Script Title",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "TargetService", "type": "string", "default": "Spooler"},
            {"name": "MaxEvents", "type": "int", "default": 20, "min": 1, "max": 500},
            {"name": "RestartService", "type": "bool", "default": false}
        ]
    }
#>
```

- `risk_level`: Must be `"read_only"` (diagnostics) or `"remediation"` (modifies system state; triggers UI confirmation).
- `ps_edition`: `"Desktop"` (`powershell.exe` 5.1 for maximum RMM compatibility) or `"Core"` (`pwsh.exe` 7+).

### 4.2 Precise PowerShell Error Handling
1. Always include `[CmdletBinding()]` and a typed `param(...)` block matching `.PSSTORE_META.params`.
2. Always set `$ErrorActionPreference = 'Stop'` at the top of the script.
3. Wrap all operational logic in `try / catch / finally` blocks.
4. Pass `-ErrorAction Stop` explicitly to every cmdlet inside the `try` block so non-terminating errors are caught reliably.
5. Never hardcode credentials, API keys, or tenant secrets.

### 4.3 Standard Output Envelope & Dual-Purpose Template
Scripts should support both RMM execution and local structured output:

```powershell
<#
.SYNOPSIS
    Clears stuck print jobs and restarts the Print Spooler service.
.PSSTORE_META
    {
        "title": "Reset Print Spooler",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 30,
        "output_mode": "text",
        "params": [
            {"name": "ClearQueueFiles", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$ClearQueueFiles = $true
)

$ErrorActionPreference = 'Stop'

try {
    Stop-Service -Name Spooler -Force -ErrorAction Stop
    if ($ClearQueueFiles) {
        $spoolPath = "$env:SystemRoot\System32\spool\PRINTERS\*"
        Remove-Item -Path $spoolPath -Force -ErrorAction Stop
    }
    Start-Service -Name Spooler -ErrorAction Stop
    Write-Output "[SUCCESS] Print Spooler restarted. Queue cleared: $ClearQueueFiles"
}
catch {
    Write-Error "[ERROR] Failed to reset Print Spooler: $($_.Exception.Message)"
    exit 1
}
finally {
    # Ensure service status is always reported for RMM activity logs
    Get-Service -Name Spooler | Select-Object Name, Status, StartType
}
```

Or when structured JSON is preferred:
```powershell
$payload = @{
    status  = "pass" # "pass", "warning", "fail", or "error"
    summary = "Human-readable one-line outcome."
    data    = @($results)
    errors  = @()
}
$payload | ConvertTo-Json -Depth 4 -Compress
```

`runner.py` intelligently detects whether the output is a JSON envelope or standard RMM console output with exit codes.

### 4.4 Tabular & Human-Readable Structured Output Rule
When a script gathers multi-item inventory or tabular diagnostic data (e.g., device drivers, network interfaces, event logs, disk partitions, local accounts):
1. **Human-Readable Table First:** Format and write a clean table to `stdout` (e.g., using `$results | Format-Table -AutoSize | Out-String | Write-Output`) before emitting the JSON envelope. This ensures technicians running the script in an RMM terminal or viewing the Raw Console see an immediate, human-readable ASCII table instead of a dense raw string.
2. **Structured JSON Envelope Last:** Always emit the single-line JSON envelope `$payload | ConvertTo-Json -Depth 4 -Compress` as the very last line of `stdout`.
3. **Flat Objects in `data`:** The `data` property in `$payload` MUST be an array of flat `[PSCustomObject]` dictionaries with consistent, PascalCase property keys (e.g. `DeviceName`, `DeviceClass`, `DriverVersion`). Never put nested raw strings or unparsed blobs inside `data`. This guarantees the PySide6 `Structured Results` view automatically builds a multi-column, sortable and resizable table widget.

---

## 5. UI & Coding Standards
- **Python Version & Typing:** Python 3.11+ with type hints (`str | None`, `list[dict]`, `@dataclass`).
- **Dark Mode Theme:** Clean, high-contrast dark theme (`#111827` background, `#1f2937` panels, `#2563eb` primary buttons) using `Consolas` for code and console views.
- **Three Core Action Bar Actions:**
  1. **Copy Raw Script to Clipboard:** Copies the exact `.ps1` file content from disk (`QGuiApplication.clipboard().setText()`).
  2. **Copy RMM-Ready Script (With Injected Parameters):** Reads UI parameter form values, injects them directly into the script's `param()` defaults in memory, and copies a standalone ready-to-run script.
  3. **Test Locally on My PC:** Executes the script via non-blocking `QProcess` in a local sandbox with elevation awareness and a safety gate for `remediation` scripts.
