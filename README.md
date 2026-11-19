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
  - **Global `Win+F8` Hotkey (`services/hotkey_service.py`):** Bring PowerShellStore onto the screen or minimize it from anywhere in Windows using Win32 `RegisterHotKey`.
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
│   ├── hotkey_service.py        # System-wide Win+F8 Win32 RegisterHotKey & native event filter
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
└── tests/                       # Automated pytest suite (38 tests across all layers)
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

# Silent background startup to system tray (press Win+F8 to toggle)
pythonw main.py --startup
```

### Verification Commands
```powershell
# Run the full automated test suite (38 tests)
python -m pytest tests/ -v

# Lint all PowerShell scripts against the .PSSTORE_META and PS 5.1 AST contract
python tools/lint_scripts.py
```

---

## ⌨️ Keyboard Shortcuts

PowerShellStore includes global and workstation keyboard shortcuts for fast triage. Standard text-editing shortcuts (`Ctrl+C`, `Ctrl+V`, `Ctrl+X`, `Ctrl+A`, `Ctrl+Z`) are intentionally left untouched so they continue working normally inside search fields, parameter inputs, **Raw Console**, and **Script Source** previews.

### Global Windows Shortcut
| Shortcut | Scope | Action / Function | Behavior & Notes |
| :--- | :--- | :--- | :--- |
| `Win+F8` | Global (OS-wide) | **Show / Minimize PowerShellStore** (`services/hotkey_service.py` → `toggle_window_visibility`) | Registered via Win32 `RegisterHotKey`. Restores/brings the window to the foreground from tray or minimized state, or minimizes it if already active. |

### Navigation & Catalog
| Shortcut | Scope | Action / Function | Behavior & Notes |
| :--- | :--- | :--- | :--- |
| `Ctrl+B` | In-App | **Toggle Sidebar** (`toggle_sidebar`) | Collapses or expands the left Categories & Filters sidebar to maximize catalog/workstation width. |
| `Ctrl+F` | In-App | **Focus Search Box** (`_focus_search_input`) | Automatically expands the sidebar if collapsed, focuses the search input, and selects existing query text. |
| `F5` | In-App | **Sync Catalog** (`sync_and_refresh`) | Rescans all `scripts/` subfolders, updates SHA-256 checksums in SQLite, and refreshes counts. |
| `Esc` | In-App | **Stop / Clear Search** (`_handle_escape`) | Context-aware: stops the active script if currently running; otherwise clears any active search filter and returns focus to the catalog table. |

### Script Actions & Parameters
| Shortcut | Scope | Action / Function | Behavior & Notes |
| :--- | :--- | :--- | :--- |
| `Ctrl+Shift+C` | In-App | **Copy Raw Script** (`_on_copy_raw_clicked`) | Copies the exact unmodified `.ps1` file from disk to the Windows Clipboard. |
| `Ctrl+Shift+R` | In-App | **Copy RMM-Ready Script** (`_on_copy_rmm_clicked`) | Injects current UI parameter values into the script's `param()` defaults in memory and copies the standalone script to the Windows Clipboard. |
| `Ctrl+Enter` *(or `Ctrl+Return`)* | In-App | **Test Locally on My PC** (`_shortcut_run_local`) | Runs the selected script locally in the non-blocking `QProcess` sandbox (respects remediation confirmations & UAC prompts; ignored if a script is already running). |
| `Shift+F5` | In-App | **Stop Script** (`_shortcut_stop_execution`) | Terminates the currently running local PowerShell script (active only while executing). |
| `Ctrl+Alt+R` | In-App | **Reset Parameter Defaults** (`_shortcut_reset_parameters`) | Restores all configurable parameters on the selected script back to their `.PSSTORE_META` defaults. |

### Workstation Tabs & Ticket Reporting
| Shortcut | Scope | Action / Function | Behavior & Notes |
| :--- | :--- | :--- | :--- |
| `Ctrl+1` | In-App | **Structured Results Tab** (`_switch_console_tab(0)`) | Switches the right workstation pane to **Structured Results**. |
| `Ctrl+2` | In-App | **Raw Console Tab** (`_switch_console_tab(1)`) | Switches the right workstation pane to **Raw Console**. |
| `Ctrl+3` | In-App | **Script Source Tab** (`_switch_console_tab(2)`) | Switches the right workstation pane to read-only **Script Source**. |
| `Ctrl+4` | In-App | **Run History Tab** (`_switch_console_tab(3)`) | Switches the right workstation pane to **Run History**. |
| `Ctrl+Shift+T` | In-App | **Copy Ticket Report** (`_shortcut_copy_report`) | Copies Rich-Text HTML + Markdown audit evidence for the active (or reloaded history) run to the Windows Clipboard. |
| `Ctrl+S` | In-App | **Save Report...** (`_shortcut_save_report`) | Opens the Save dialog to export a self-contained `.html` execution report to disk. |
| `Ctrl+L` | In-App | **Clear Raw Console** (`_shortcut_clear_console`) | Clears all text in the **Raw Console** tab. |

### Window & Application
| Shortcut | Scope | Action / Function | Behavior & Notes |
| :--- | :--- | :--- | :--- |
| `Ctrl+=` / `Ctrl++` | In-App | **Increase Window Opacity** (`_adjust_opacity(+5)`) | Raises window opacity by `+5%` (clamped at `100%`). |
| `Ctrl+-` | In-App | **Decrease Window Opacity** (`_adjust_opacity(-5)`) | Lowers window opacity by `-5%` (clamped at `60%`). |
| `Ctrl+0` | In-App | **Reset Window Opacity** (`_reset_opacity`) | Restores window opacity immediately to `100%`. |
| `Ctrl+Q` | In-App | **Quit PowerShellStore** (`quit_application`) | Unregisters `Win+F8`, hides the tray icon, and exits completely (bypasses minimize-to-tray). |

---

## 📦 Built-In Script Catalog (38 Scripts)

All **38** built-in scripts target Windows PowerShell 5.1 (`Desktop`) for maximum RMM compatibility, pass static + PowerShell 5.1 AST contract validation via `tools/lint_scripts.py`, and wrap execution in `try / catch / finally` with `$ErrorActionPreference = 'Stop'`. Unless noted otherwise, scripts emit a human-readable ASCII table to `stdout` first, followed by a compressed single-line JSON envelope (`output_mode: json`) for PowerShellStore's **Structured Results** grid and ticket reports.

### `01_System` (11 Scripts)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Get-BatteryHealthReport.ps1` | Get Battery Health & Power Status | `read_only` · No · `30s` | `WearThresholdPercent=30` *(int, 5–80)* | Inspects `.NET PowerStatus` for live charge %, AC line status, and battery presence (reporting desktops/VMs cleanly), then runs `powercfg.exe /batteryreport /xml` when present to extract design vs. full-charge capacity (mWh), cycle count, and wear %. Raises `warning` if wear meets/exceeds threshold. |
| `Get-DiskSpaceReport.ps1` | Disk Free Space Report | `read_only` · No · `20s` | `LowSpaceThresholdPercent=15` *(int, 1–90)* | Evaluates fixed logical volumes (`Win32_LogicalDisk` via CIM with a `.NET DriveInfo` fallback) returning `DeviceID`, `VolumeName`, `TotalGB`, `FreeGB`, `PercentFree`, and `LowDiskSpace`. Flags warning status when any volume drops below `LowSpaceThresholdPercent`. |
| `Get-HardwareInventory.ps1` | Get Hardware & BIOS Inventory | `read_only` · No · `30s` | `IncludeGPU=true` *(bool)* | Gathers manufacturer, product model, motherboard, BIOS version/release date, processor name/clock/logical core count, total/free RAM and memory usage %, and (when `IncludeGPU` is true) display adapters via CIM with a read-only .NET registry fallback. |
| `Get-HighResourceProcesses.ps1` | Get High-Resource Processes | `read_only` · No · `20s` | `SortBy="CPU"` *(string: `CPU` \| `Memory`)*, `TopCount=10` *(int, 1–50)* | Audits running processes via `Get-Process` sorted by CPU seconds or Working Set memory, reporting PID, process name, `CPUSec`, `WorkingSetMB`, `PrivateMemMB`, company, and executable path (gracefully handling protected system processes). |
| `Get-OSInformation.ps1` | Get Operating System Information | `read_only` · No · `30s` | `Detailed=true` *(bool)* | Collects OS edition/caption, DisplayVersion, build number (distinguishing Windows 11 from Windows 10), architecture, install date, last boot time, uptime (with CIM + `TickCount64` fallback), pending reboot indicator, and (when `Detailed` is true) registered owner/org and installed hotfix count. |
| `Get-PendingRebootStatus.ps1` | Check Pending Reboot Status | `read_only` · No · `15s` | *None* | Checks Windows registry indicators for Component-Based Servicing (`RebootPending`), Windows Update (`RebootRequired`), Pending File Rename Operations, and pending Computer Name changes, returning a consolidated `IsRebootPending` boolean summary. |
| `Get-RecentEventErrors.ps1` | Get Recent Event Log Errors | `read_only` · No · `30s` | `HoursBack=24` *(int, 1–168)*, `MaxEvents=30` *(int, 5–100)* | Queries `Get-WinEvent` across both `System` and `Application` logs for `Critical` (Level 1) and `Error` (Level 2) records within the lookback window, outputting timestamp, log name, severity, Event ID, provider, and message. |
| `Get-StartupApplications.ps1` | Get Startup Applications & Tasks | `read_only` · No · `25s` | `IncludeScheduledTasks=true` *(bool)* | Enumerates auto-start items from `HKCU` and `HKLM` `Run` registry keys, user Startup folder shortcuts, and optionally logon/boot-triggered Scheduled Tasks (`Get-ScheduledTask`), detailing source, command, user scope, and enabled status. |
| `Get-SystemCrashHistory.ps1` | Get System Crash & BSOD History | `read_only` · **Yes** · `30s` | `MaxDays=30` *(int, 1–90)* | Inspects `C:\Windows\Minidump\*.dmp` files and `System` Event Log crash entries (`Id` `1001` BugCheck & `41` Kernel-Power unclean shutdown) within `MaxDays`, sorting chronologically descending for BSOD root-cause triage. |
| `Invoke-DeepSystemCleanup.ps1` | Deep System Cleanup & Health Repair | `remediation` · **Yes** · `600s` | `ClearUserTemps=true`, `ClearSystemTemp=true`, `ClearWindowsUpdateCache=true`, `EmptyRecycleBins=true`, `RunDismCleanup=true`, `RunSfcScan=true` *(all bool)* | Safely clears all user profile Temp folders, `%SystemRoot%\Temp`, Windows Update `SoftwareDistribution\Download` cache, and Recycle Bins (with shell fallback), runs `DISM /Online /Cleanup-Image /StartComponentCleanup` and `sfc /scannow`, and measures before/after drive space to report MB and GB reclaimed. |
| `Update-Windows.ps1` | Install Windows Updates | `remediation` · **Yes** · `900s` | `ScanOnly=false` *(bool)*, `AutoReboot=false` *(bool)*, `MaxUpdates=25` *(int, 1–100)* | Uses the native Windows Update Agent COM API (`Microsoft.Update.Session`) to search, accept EULAs, download, and install pending software/security updates (or audit pending KBs without installing when `ScanOnly=true`). Reports KB IDs, MB size, result status, `reboot_required`, and triggers a 60s restart if `AutoReboot=true`. |

### `02_Network` (6 Scripts)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Get-ListeningPorts.ps1` | Get Active Listening Ports | `read_only` · No · `20s` | `Protocol="All"` *(string: `All` \| `TCP` \| `UDP`)*, `PortFilter=0` *(int, 0–65535; `0`=all)* | Lists active TCP listeners (`Get-NetTCPConnection`) and UDP endpoints (`Get-NetUDPEndpoint`) filtered by protocol or port, mapped to local address, PID, process name, and executable path (with `netstat.exe -ano` fallback when CIM/NetTCPIP is restricted). |
| `Get-NetworkSnapshot.ps1` | Get Network & DNS Snapshot | `read_only` · No · `20s` | `AdapterName="*"` *(string wildcard)* | Collects matching network adapters (`Get-NetAdapter` with `.NET NetworkInterface` fallback), reporting operational status, link speed, MAC address, and configured IPv4/IPv6 DNS servers (`Get-DnsClientServerAddress`). |
| `Get-WiFiDiagnostics.ps1` | Get Wi-Fi Health & Signal Diagnostics | `read_only` · No · `25s` | `PingGateway=true` *(bool)* | Queries `netsh wlan show interfaces` to extract connection state, SSID, BSSID, signal strength %, radio type (802.11ax/ac/etc.), channel, and Tx/Rx link rates (Mbps), and optionally discovers (`Get-NetRoute`) and pings the default gateway for wireless latency. Gracefully handles desktops without Wi-Fi. |
| `Reset-NetworkStack.ps1` | Reset Network Stack & Flush DNS | `remediation` · **Yes** · `60s` | `FlushDNS=true`, `RenewDHCP=true`, `ResetWinsock=true`, `ResetTCPStack=true` *(all bool)* | Executes selectable network stack repair steps (`ipconfig /flushdns` + `/registerdns`, `/release` + `/renew`, `netsh winsock reset`, and `netsh int ip reset`) and reports per-step outcomes to resolve DNS/DHCP dropouts and Winsock corruption. |
| `Test-NetworkQuality.ps1` | Test Network Quality & Jitter | `read_only` · No · `45s` | `TargetHost="1.1.1.1"`, `PingCount=10` *(int, 4–50)*, `MaxAcceptableLatencyMs=100` *(int, 10–1000)* | Resolves `TargetHost`, runs a burst of ICMP echo probes (automatically falling back to TCP socket latency probes on port 443/80 if ICMP is blocked), computes min/avg/max latency, jitter (mean successive difference), and packet loss %, and assigns an overall `QualityRating`. |
| `Test-PortConnectivity.ps1` | Test TCP Port Connectivity | `read_only` · No · `15s` | `TargetHost="1.1.1.1"`, `Port=443` *(int, 1–65535)*, `TimeoutMs=3000` *(int, 500–15000)* | Opens an asynchronous .NET `System.Net.Sockets.TcpClient` connection test to `TargetHost:Port` with explicit millisecond timeout control, reporting boolean reachability (`Connected`) and measured handshake response time in ms. |

### `03_M365` (7 Scripts)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Clear-BrowserCache.ps1` | Clear Browser Cache (Edge & Chrome) | `remediation` · No · `30s` | `TargetBrowser="All"` *(string: `All` \| `Edge` \| `Chrome`)*, `CloseRunningBrowsers=true` *(bool)* | Optionally terminates running `msedge`/`chrome` processes to unlock files and purges `Cache`, `Code Cache`, and `GPUCache` directories under the user's `Default` profile while preserving bookmarks, saved passwords, and history. Reports MB freed per cache root. |
| `Clear-OutlookCache.ps1` | Clear Microsoft Outlook Cache | `remediation` · No · `60s` | `CloseOutlook=true`, `ClearAttachmentTemp=true`, `ClearRoamCache=true`, `PreserveAutoComplete=true`, `ClearOfflineAddressBook=true`, `ClearFormsCache=true` *(all bool)* | Safely terminates Outlook and clears `Content.Outlook` attachment temp files, `RoamCache` (preserving `Stream_Autocomplete_*.dat` nickname cache by default), Offline Address Books, Forms cache, and New Outlook (`OLK`) `LocalCache`. Reports deleted file count and MB freed. |
| `Clear-TeamsCache.ps1` | Clear Microsoft Teams Cache | `remediation` · No · `30s` | `KillRunningProcesses=true`, `RelaunchTeams=false` *(both bool)* | Terminates running Classic (`Teams`) and New Teams (`ms-teams`) processes, purges cache subfolders under `%APPDATA%\Microsoft\Teams` and `%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams`, and optionally relaunches `ms-teams:`. |
| `Get-EntraRegistrationStatus.ps1` | Get Entra ID Join & Device Status | `read_only` · No · `20s` | *None* | Runs native `dsregcmd.exe /status` and parses `AzureAdJoined`, `EnterpriseJoined`, `DomainJoined`, `DeviceId`, and `TenantName` into clean columns for Microsoft Entra ID / Hybrid Join and PRT diagnostics. |
| `Get-OfficeActivationStatus.ps1` | Get Office & M365 Activation Status | `read_only` · No · `30s` | `CheckVolumeLicensing=true` *(bool)* | Reads Office Click-to-Run registry configuration (version, bitness, installed product release IDs, Shared Computer Licensing, signed-in corporate identity) and optionally queries `OSPP.VBS` via `cscript` for volume/KMS license state and partial product key. |
| `Get-OutlookAddins.ps1` | Get Outlook COM Add-ins & Cache Status | `read_only` · No · `20s` | `CheckOSTSize=true` *(bool)* | Audits HKCU/HKLM Outlook COM Add-ins (`ProgId`, human-readable name, scope, and `LoadBehavior` decoded into load mode descriptions) and optionally inspects local `.ost` mailbox file sizes under `%LOCALAPPDATA%\Microsoft\Outlook` to pinpoint startup slowdowns. |
| `Reset-OneDriveSync.ps1` | Reset Microsoft OneDrive Sync | `remediation` · No · `45s` | `KillRunningProcess=true`, `RunResetCommand=true`, `RelaunchOneDrive=true` *(all bool)* | Stops stuck `OneDrive.exe` processes, cleans temporary sync lock/cache artifacts without deleting user files, runs `OneDrive.exe /reset`, and relaunches the OneDrive sync client. |

### `04_Devices` (6 Scripts)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Get-DeviceDrivers.ps1` | Get Installed Device Drivers | `read_only` · No · `45s` | `DeviceClass="*"` *(wildcard)*, `OnlySigned=false` *(bool)*, `MaxResults=50` *(int, 1–1000)* | Inventories installed PnP drivers with `DeviceName`, `DeviceClass`, `Manufacturer`, `DriverVersion`, `DriverDate`, `InfName`, and `IsSigned` using 3 resilient tiers: CIM `Win32_PnPSignedDriver` → Registry Class keys → `driverquery` fallback. |
| `Get-DisplayTopology.ps1` | Get Display & Monitor Topology | `read_only` · No · `20s` | *None* | Enumerates active monitors via `System.Windows.Forms.Screen` paired with active GPU controllers (`Win32_VideoController` via CIM with read-only registry fallback), reporting display name, primary screen flag, desktop resolution, refresh rate (Hz), bits per pixel, and GPU adapter. |
| `Get-PrintQueues.ps1` | Get Print Queues & Stuck Jobs | `read_only` · No · `30s` | `IncludeJobs=true`, `OnlyWithJobs=false` *(both bool)* | Inspects installed printers (`Get-Printer`) and queued/stuck jobs (`Get-PrintJob`), falling back to `.NET PrinterSettings` + Spooler `.SHD`/`.SPL` count estimation if PrintManagement cmdlets are unavailable. Reports port, driver, default/shared status, job counts, and pending document details. |
| `Get-ProblemDevices.ps1` | Get Problem Devices (Device Manager Errors) | `read_only` · No · `20s` | `IncludeDisabled=false` *(bool)* | Queries `Win32_PnPEntity` where `ConfigManagerErrorCode <> 0` (optionally hiding intentional Code 22 disabled devices) and translates Device Manager error codes (e.g., Code 10, 28, 39, 43) into actionable descriptions with Device ID, class, and manufacturer. |
| `Reset-PrintSpooler.ps1` | Reset Print Spooler | `remediation` · **Yes** · `30s` | `ClearQueueFiles=true` *(bool)* | **Output Mode: `text`.** Stops the Windows `Spooler` service, optionally deletes hung spool files from `%SystemRoot%\System32\spool\PRINTERS\*`, restarts `Spooler`, and outputs final service `Name`, `Status`, and `StartType` in the `finally` block for RMM logs. |
| `Update-DeviceDrivers.ps1` | Update All Device Drivers | `remediation` · **Yes** · `600s` | `IncludeOptional=true`, `RescanPnPDevices=true`, `RebootIfRequired=false` *(all bool)* | Uses `Microsoft.Update.Session` (`Type='Driver'`) to download and install pending Windows Update hardware drivers (optionally filtering optional/browse-only drivers), triggers `pnputil.exe /scan-devices` for PnP re-matching, and schedules a 60s reboot only if both `RebootIfRequired` and `reboot_required` are true. |

### `05_Security_Defender` (7 Scripts)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Get-BitLockerStatus.ps1` | Get BitLocker Encryption Status | `read_only` · **Yes** · `30s` | `MountPoint=""` *(string; empty = all volumes)* | Queries `Get-BitLockerVolume` (automatically falling back to `manage-bde.exe -status`) to audit mount point, volume type, encryption percentage, volume/protection status, and configured key protectors (e.g., TPM, RecoveryPassword). |
| `Get-DefenderStatus.ps1` | Get Microsoft Defender Status | `read_only` · No · `20s` | *None* | Queries `Get-MpComputerStatus` to verify Antivirus, Antispyware, and Real-Time Protection states alongside engine version, signature version, last signature update timestamp, and signature age in days. |
| `Get-ExpiringCertificates.ps1` | Get Expiring & Expired Certificates | `read_only` · No · `20s` | `DaysThreshold=30` *(int, 1–180)* | Scans `Cert:\LocalMachine\My` and `Cert:\CurrentUser\My` personal stores to flag certificates that are already expired or expiring within `DaysThreshold` days, outputting store, subject, issuer, expiration date, days remaining, and thumbprint. |
| `Get-FirewallStatus.ps1` | Get Windows Firewall Status | `read_only` · No · `30s` | `CheckAllProfiles=true` *(bool)* | Checks Windows Firewall operational state, default inbound/outbound actions, and `AllowInboundRules` across `Domain`, `Private`, and `Public` profiles (or currently active network profiles via `Get-NetConnectionProfile`), falling back to `HKLM` FirewallPolicy registry keys if needed. |
| `Get-LocalAccountStatus.ps1` | Get Local Account & Password Status | `read_only` · **Yes** · `20s` | *None* | Audits local user accounts (`Get-LocalUser` with `ADSI WinNT://` fallback) and reads SAM lockout state directly via ADSI (compensating for PS 5.1 `Get-LocalUser` omitting `LockedOut`), reporting enabled state, lockout status, password age in days, expiration policy, and last logon. |
| `Get-LocalAdministrators.ps1` | Audit Local Administrators | `read_only` · **Yes** · `20s` | `IncludeBuiltInAdmin=true` *(bool)* | Enumerates members of the local `Administrators` group via `Get-LocalGroupMember` (with ADSI fallback), classifying each account as `Local`, `Active Directory Domain`, or `Microsoft Entra ID` alongside `ObjectClass` and `SID` (flagging warning when more than 3 admins exist). |
| `Invoke-DefenderUpdateAndScan.ps1` | Update Defender Signatures & Trigger Scan | `remediation` · **Yes** · `300s` | `ScanType="QuickScan"` *(string: `QuickScan` \| `FullScan`)*, `UpdateSignatures=true` *(bool)* | Optionally updates Defender definitions (`Update-MpSignature`), executes an on-demand `Start-MpScan` (`MpCmdRun.exe` fallback), and checks `Get-MpThreatDetection` to report any detected threats and remediation status. |

### `99_Custom` (1 Script)
| Script | Title | Risk / Admin | Parameters (Defaults & Range) | Explanation & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `Sample-CustomDiagnostic.ps1` | Sample Custom Diagnostic | `read_only` · No · `15s` | `Message="Hello from PowerShellStore"` *(string)* | Minimal starter template demonstrating the mandatory `.PSSTORE_META` block, typed `param()`, CIM query (`Win32_OperatingSystem` with `$env:PROCESSOR_ARCHITECTURE` fallback), ASCII table output, and single-line JSON envelope (echoes `Message`, `ComputerName`, `UserName`, `OSArchitecture`, and timestamp). |

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
