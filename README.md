# PowerShellStore ⚡

A Windows-focused **PySide6** desktop application built for IT helpdesk and Managed Service Provider (MSP) technicians. 

PowerShellStore bridges the gap between local script prototyping and production deployment on remote endpoints via Remote Monitoring and Management (RMM) tools like NinjaOne, Datto RMM, ConnectWise Automate, and N-central.

---

## 🚀 Key Features

- **Categorized Script Catalog:** Instant search, risk level filtering (`read_only` vs `remediation`), and PowerShell edition filtering (`Desktop` 5.1 vs `Core` 7+).
- **Dynamic Parameter Forms:** Typed inputs (`string`, `int`, `bool`) generated automatically from `.PSSTORE_META` comment blocks.
- **Dual-Mode Windows Clipboard:**
  - **Copy Raw Script:** Copies the pristine `.ps1` directly from disk.
  - **Copy RMM-Ready Script:** Automatically injects the UI form parameter values into the `param()` block defaults in-memory before copying.
- **Local Testing Sandbox:**
  - Non-blocking `QProcess` runner with live output streaming.
  - Safety gates and UAC elevation prompts for scripts requiring Administrator privileges.
  - Structured output parsing supporting both table/JSON envelopes and standard RMM console logs.
- **File-First Architecture:** Real `.ps1` files on disk are the single source of truth; SQLite indexes metadata and SHA-256 hashes incrementally.
- **Dark Theme Desktop Workstation:** 3-Pane master layout with collapsible sidebar (`Ctrl+B`), resizable table columns, and adjustable window opacity slider.

---

## 📁 Repository Structure

```text
PowerShellStore/
├── data/                    # SQLite database storage (powershell_store.db)
├── repositories/            # Persistence layer (catalog_repo.py)
├── services/                # Business logic (scanner.py, runner.py, clipboard_service.py)
├── ui/                      # PySide6 presentation layer (launcher, sidebar, tables, console)
├── scripts/                 # Categorized PowerShell scripts
│   ├── 01_System/           # Disk space, uptime, pending reboots, cleanup
│   ├── 02_Network/          # DNS, TCP latency, network snapshots
│   ├── 03_M365/             # Teams cache, Outlook cache, Entra ID join status
│   ├── 04_Devices/          # Print spooler, driver inventory, driver updater
│   ├── 05_Security_Defender/# Defender status, local admins, BitLocker
│   └── 99_Custom/           # User-created & experimental scripts
├── tests/                   # Automated pytest suite
├── main.py                  # Desktop application entry point
├── requirements.txt         # Python dependencies
└── RULES.md                 # Antigravity architectural contract
```

---

## 🛠️ Quick Start

### Prerequisites
- Windows 10 / 11 / Server 2016+
- Python 3.11 or higher
- PowerShell 5.1 (or PowerShell 7+)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/JDecelles1990/PowerShellStore.git
   cd PowerShellStore
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Launch the application:
   ```bash
   python main.py
   ```

4. Run the test suite:
   ```bash
   pytest tests/ -v
   ```

---

## 📜 PowerShell Script Contract (`.PSSTORE_META`)

Every script under `scripts/` includes a structured header:

```powershell
<#
.SYNOPSIS
    Brief one-line summary of what the script does.
.PSSTORE_META
    {
        "title": "Human-Readable Script Title",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 30,
        "output_mode": "json",
        "params": [
            {"name": "TargetParameter", "type": "string", "default": "Value"}
        ]
    }
#>
```

---

## 📄 License
MIT License. Built for IT professionals and MSPs.
