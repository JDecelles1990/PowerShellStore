# PowerShellStore ⚡

A Windows-focused **PySide6** desktop workstation built for IT helpdesk and Managed Service Provider (MSP) technicians.

**PowerShellStore** bridges the gap between local script validation and remote endpoint execution via Remote Monitoring and Management (RMM) platforms (NinjaOne, Datto RMM, ConnectWise Automate, N-central, Intune, etc.).

---

## 🚀 Key Features

- **38 Ready-to-Use Scripts Across 6 Categories:** Production-ready diagnostics and remediations for `System`, `Network`, `M365`, `Devices`, `Security_Defender`, and `Custom` workflows.
- **File-First Architecture with Live Sync:** Real `.ps1` files under `scripts/` are the single source of truth. [`ScriptScanner`](services/scanner.py) parses embedded `.PSSTORE_META` JSON headers, computes SHA-256 hashes, and indexes scripts into SQLite (`data/powershell_store.db`) automatically via `QFileSystemWatcher`.
- **Dynamic Parameter Forms:** Generates typed UI controls (`string`, `int` with bounds, `bool`) directly from each script's `.PSSTORE_META.params` schema.
- **Dual-Mode Windows Clipboard (`services/clipboard_service.py`):**
  - **Copy Raw Script:** Copies the exact `.ps1` file from disk.
  - **Copy RMM-Ready Script:** Injects customized UI parameter values directly into the script's `param(...)` block defaults in-memory for immediate pasting into RMM tools.
- **Local Testing Sandbox (`services/runner.py`):**
  - Non-blocking `QProcess` execution with live stdout/stderr streaming and configurable per-script `QTimer` timeouts.
  - Safety confirmation gates for `remediation` scripts and optional UAC elevation launch (`execute_script_elevated`) when `requires_admin` is true.
  - Automatically parses dual-purpose output: formatted ASCII tables in **Raw Console**, structured objects in **Structured Results**, and full SQLite execution history in **Run History**.
- **Ticketing & Audit Export Reports (`services/report_service.py`):**
  - **Copy Ticket Report:** Places both Rich-Text HTML (with audit header, status badge, and styled evidence table) and Markdown on the clipboard simultaneously via `QMimeData`—ready to paste into ConnectWise, ServiceNow, Jira, or Outlook.
  - **Save Report...:** Exports self-contained offline `.html` audit reports to disk.
  - Works on both live runs and historical executions reloaded from **Run History**.
- **Windows Desktop & Tray Integration:**
  - **Global `Shift+F8` Hotkey (`services/hotkey_service.py`):** Show/hide PowerShellStore from anywhere in Windows using Win32 `RegisterHotKey`.
  - **Start with Windows (`services/startup_service.py`):** Toggle launch-on-login via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` using silent `pythonw.exe main.py --startup` tray startup.
  - **System Tray (`QSystemTrayIcon`):** Minimize-to-tray on close, toggle visibility, toggle startup setting, or quit cleanly.
- **Modern Dark Workstation UI (`ui/`):**
  - 3-pane layout with collapsible sidebar (`Ctrl+B`), resizable tables, and a **60%–100% window opacity slider**.
  - Animated hover gradient, rainbow glow halo, diagonal shine sweep, and click ripple effects across push buttons and list/table rows (`ui/effects.py`, `ui/styles.py`).
- **Built-In Static & AST Contract Linter (`tools/lint_scripts.py`):** Validates every `.ps1` script against `.PSSTORE_META`, PowerShell 5.1 syntax (`Parser::ParseFile`), `try/catch/finally` error handling, parameter usage, and dual table/JSON output rules.

---

## 📁 Architecture & Repository Structure

`PowerShellStore` enforces strict layer boundaries so PySide6 presentation code never touches SQLite (`sqlite3`), subprocesses (`subprocess`), or hashing (`hashlib`) directly:

```text
ui/ (PySide6 Presentation) ──► services/ (Scanner, Runner, Clipboard, Report, Hotkey, Startup) ──► repositories/ (SQLite Persistence)
```

```text
PowerShellStore/
├── main.py                      # Application entry point (--startup / --minimized / --tray supported)
├── requirements.txt             # Python dependencies (PySide6, shiboken6, pytest)
├── GEMINI.md                    # Workspace AI & architectural contract instructions
├── RULES.md                     # Architectural rules & PowerShell script contract
├── data/                        # Local SQLite database (powershell_store.db, gitignored)
├── repositories/
│   └── catalog_repo.py          # SQLite schema, parameterized CRUD, and run_history persistence
├── services/
│   ├── scanner.py               # Scans scripts/ subfolders, parses .PSSTORE_META, SHA-256 sync
│   ├── clipboard_service.py     # Raw copy & in-memory param() block injector for RMM deployment
│   ├── runner.py                # Non-blocking QProcess runner, UAC elevation & output envelope parser
│   ├── report_service.py        # Rich-text HTML + Markdown ticket evidence generator & file exporter
│   ├── hotkey_service.py        # System-wide Shift+F8 Win32 RegisterHotKey & native event filter
│   └── startup_service.py       # Windows HKCU Run registry toggle (pythonw.exe silent startup)
├── ui/
│   ├── launcher_view.py         # Main 3-pane coordinator, tray icon, opacity slider & watcher wiring
│   ├── sidebar_view.py          # Categories, live search, risk/edition filters, startup checkbox
│   ├── catalog_table_view.py    # Script catalog table with Risk & Admin status indicators
│   ├── parameter_form.py        # Dynamic typed parameter inputs generated from .PSSTORE_META
│   ├── console_view.py          # Tabbed output: Structured Results, Raw Console, Source, Run History
│   ├── styles.py                # Dark theme QSS stylesheet + gradient button states
│   └── effects.py               # Animated button glow/ripple & hovering list/table row delegate
├── scripts/                     # Categorized PowerShell script library (source of truth)
│   ├── 01_System/               # 11 scripts
│   ├── 02_Network/              # 6 scripts
│   ├── 03_M365/                 # 7 scripts
│   ├── 04_Devices/              # 6 scripts
│   ├── 05_Security_Defender/    # 7 scripts
│   └── 99_Custom/               # 1 script
├── tools/
│   └── lint_scripts.py          # Static & PowerShell 5.1 AST contract linter CLI
└── tests/                       # Automated pytest suite (31 tests across all layers)
```

---

## 🛠️ Quick Start

### Prerequisites
- **OS:** Windows 10 / Windows 11 / Windows Server 2016+
- **Python:** 3.11 or higher (uses standard library `sqlite3`, `ctypes`, `winreg`, `hashlib`, etc.)
- **PowerShell:** Windows PowerShell 5.1 (`powershell.exe`, default for maximum RMM compatibility) and/or PowerShell 7+ (`pwsh.exe`)

### Installation
1. Clone the repository:
   ```powershell
   git clone https://github.com/JDecelles1990/PowerShellStore.git
   cd PowerShellStore
   ```

2. Create and activate a virtual environment (recommended):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install Python dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

### Running the Application
```powershell
# Normal windowed launch
python main.py

# Silent background startup to system tray (press Shift+F8 to toggle)
pythonw main.py --startup
```

### Verification Commands
```powershell
# Run the full automated test suite (31 tests)
python -m pytest tests/ -v

# Lint all PowerShell scripts against the .PSSTORE_META and PS 5.1 AST contract
python tools/lint_scripts.py
```

---

## 📦 Built-In Script Catalog (38 Scripts)

### `01_System` (11)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Get-BatteryHealthReport.ps1` | Get Battery Health & Power Status | `read_only` | No |
| `Get-DiskSpaceReport.ps1` | Disk Free Space Report | `read_only` | No |
| `Get-HardwareInventory.ps1` | Get Hardware & BIOS Inventory | `read_only` | No |
| `Get-HighResourceProcesses.ps1` | Get High-Resource Processes | `read_only` | No |
| `Get-OSInformation.ps1` | Get Operating System Information | `read_only` | No |
| `Get-PendingRebootStatus.ps1` | Check Pending Reboot Status | `read_only` | No |
| `Get-RecentEventErrors.ps1` | Get Recent Event Log Errors | `read_only` | No |
| `Get-StartupApplications.ps1` | Get Startup Applications & Tasks | `read_only` | No |
| `Get-SystemCrashHistory.ps1` | Get System Crash & BSOD History | `read_only` | Yes |
| `Invoke-DeepSystemCleanup.ps1` | Deep System Cleanup & Health Repair | `remediation` | Yes |
| `Update-Windows.ps1` | Install Windows Updates | `remediation` | Yes |

### `02_Network` (6)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Get-ListeningPorts.ps1` | Get Active Listening Ports | `read_only` | No |
| `Get-NetworkSnapshot.ps1` | Get Network & DNS Snapshot | `read_only` | No |
| `Get-WiFiDiagnostics.ps1` | Get Wi-Fi Health & Signal Diagnostics | `read_only` | No |
| `Reset-NetworkStack.ps1` | Reset Network Stack & Flush DNS | `remediation` | Yes |
| `Test-NetworkQuality.ps1` | Test Network Quality & Jitter | `read_only` | No |
| `Test-PortConnectivity.ps1` | Test TCP Port Connectivity | `read_only` | No |

### `03_M365` (7)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Clear-BrowserCache.ps1` | Clear Browser Cache (Edge & Chrome) | `remediation` | No |
| `Clear-OutlookCache.ps1` | Clear Microsoft Outlook Cache | `remediation` | No |
| `Clear-TeamsCache.ps1` | Clear Microsoft Teams Cache | `remediation` | No |
| `Get-EntraRegistrationStatus.ps1` | Get Entra ID Join & Device Status | `read_only` | No |
| `Get-OfficeActivationStatus.ps1` | Get Office & M365 Activation Status | `read_only` | No |
| `Get-OutlookAddins.ps1` | Get Outlook COM Add-ins & Cache Status | `read_only` | No |
| `Reset-OneDriveSync.ps1` | Reset Microsoft OneDrive Sync | `remediation` | No |

### `04_Devices` (6)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Get-DeviceDrivers.ps1` | Get Installed Device Drivers | `read_only` | No |
| `Get-DisplayTopology.ps1` | Get Display & Monitor Topology | `read_only` | No |
| `Get-PrintQueues.ps1` | Get Print Queues & Stuck Jobs | `read_only` | No |
| `Get-ProblemDevices.ps1` | Get Problem Devices (Device Manager Errors) | `read_only` | No |
| `Reset-PrintSpooler.ps1` | Reset Print Spooler | `remediation` | Yes |
| `Update-DeviceDrivers.ps1` | Update All Device Drivers | `remediation` | Yes |

### `05_Security_Defender` (7)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Get-BitLockerStatus.ps1` | Get BitLocker Encryption Status | `read_only` | Yes |
| `Get-DefenderStatus.ps1` | Get Microsoft Defender Status | `read_only` | No |
| `Get-ExpiringCertificates.ps1` | Get Expiring & Expired Certificates | `read_only` | No |
| `Get-FirewallStatus.ps1` | Get Windows Firewall Status | `read_only` | No |
| `Get-LocalAccountStatus.ps1` | Get Local Account & Password Status | `read_only` | Yes |
| `Get-LocalAdministrators.ps1` | Audit Local Administrators | `read_only` | Yes |
| `Invoke-DefenderUpdateAndScan.ps1` | Update Defender Signatures & Trigger Scan | `remediation` | Yes |

### `99_Custom` (1)
| Script | Title | Risk Level | Admin |
| :--- | :--- | :--- | :---: |
| `Sample-CustomDiagnostic.ps1` | Sample Custom Diagnostic | `read_only` | No |

---

## 📜 Authoring New Scripts (`.PSSTORE_META` Contract)

Drop any `.ps1` file into a folder under `scripts/` and PowerShellStore indexes it automatically. Every script must follow the contract in `RULES.md`:

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
            {"name": "TargetName", "type": "string", "default": "Example"},
            {"name": "MaxCount", "type": "int", "default": 10, "min": 1, "max": 100},
            {"name": "VerboseAudit", "type": "bool", "default": false}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetName = "Example",

    [Parameter(Mandatory = $false)]
    [int]$MaxCount = 10,

    [Parameter(Mandatory = $false)]
    [bool]$VerboseAudit = $false
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Operational logic using -ErrorAction Stop inside try blocks
    $results.Add([PSCustomObject]@{
        Target = $TargetName
        Status = "Healthy"
    })

    # Emit human-readable table first for RMM activity logs & Raw Console
    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""

    $summary = "Completed check cleanly for $TargetName."
}
catch {
    $status = "error"
    $summary = "Operation failed: $($_.Exception.Message)"
    $errors.Add($_.Exception.Message)
}
finally {
    # Emit compressed single-line JSON envelope last for Structured Results & Ticket Reports
    $payload = @{
        status  = $status
        summary = $summary
        data    = @($results)
        errors  = @($errors)
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
}
```

Validate any new or modified script before committing:
```powershell
python tools/lint_scripts.py
```

---

## 📄 License
MIT License. Built for IT professionals and MSP technicians.
