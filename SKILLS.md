# PowerShellStore Script Authoring & Batch Scripting Skill (`SKILLS.md`)

A practical contract and runbook for humans and AI assistants creating, updating, or auditing PowerShell (`.ps1`) scripts for **PowerShellStore**.

Following every rule in this guide guarantees that a script:
1. Automatically indexes into `data/powershell_store.db` via [`ScriptScanner`](services/scanner.py).
2. Generates valid UI parameter controls in [`ParameterFormWidget`](ui/parameter_form.py).
3. Supports **Copy Raw Script**, **Copy RMM-Ready Script**, and **Multi-Script Combined Clipboard Bundles** via [`ClipboardService`](services/clipboard_service.py).
4. Runs reliably as both a standalone check and inside **Sequential Local / Single-UAC Batch Runs** via [`ScriptRunner`](services/runner.py).
5. Produces Rich-Text HTML & Markdown ticket evidence via [`ReportService`](services/report_service.py).
6. Passes all checks in [`tools/lint_scripts.py`](tools/lint_scripts.py).

---

## 1. When to Use This Guide

Use this guide whenever you:
- Add a new `.ps1` diagnostic or remediation script under `scripts/`.
- Modify parameters, error handling, or output formatting on an existing `.ps1` script.
- Audit scripts for **PowerShell 5.1 (`Desktop`)** compatibility or **multi-script batch execution** safety.

---

## 2. File Location, Encoding & Naming

- **File-First Source of Truth:** Always create real `.ps1` files inside one of the numbered category folders under `scripts/` (never insert raw SQL rows directly):
  - `scripts/01_System/` — Disk space, battery, OS/hardware info, pending reboots, event logs, cleanup, Windows Update.
  - `scripts/02_Network/` — NIC/DNS snapshots, Wi-Fi health, listening ports, ping/jitter, TCP port probes, stack resets.
  - `scripts/03_M365/` — Entra ID (`dsregcmd`), Office activation, Outlook add-ins/cache, Teams cache, browser cache, OneDrive.
  - `scripts/04_Devices/` — Device drivers, display topology, problem devices, print queues, spooler reset, driver updates.
  - `scripts/05_Security_Defender/` — BitLocker, Defender status/scans, certificates, firewall profiles, local accounts/admins.
  - `scripts/99_Custom/` — Technician-created, experimental, or client-specific scripts.
- **Category Derivation:** `services/scanner.py` automatically strips the numeric prefix (e.g., `04_Devices` → `Devices`) unless `"category"` is explicitly set in `.PSSTORE_META`.
- **File Naming:** Use standard PowerShell `Verb-Noun.ps1` PascalCase naming (e.g., `Get-ServiceHealth.ps1`, `Clear-PrintJobs.ps1`).
- **Encoding:** Save `.ps1` files as **UTF-8 (no BOM)** with Windows CRLF or LF line endings.

---

## 3. Mandatory `.PSSTORE_META` Header & `param(...)` Contract

### 3.1 Comment Header Placement & Metadata Schema
Every script **MUST** begin at the top of the file with a `<# ... #>` comment block containing `.SYNOPSIS` and `.PSSTORE_META`:

```powershell
<#
.SYNOPSIS
    Concise one-line description of what this script inspects or remediates.
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
            {"name": "IncludeDisabled", "type": "bool", "default": false}
        ]
    }
#>
```

| Field | Required | Allowed Values / Type | Purpose & Impact in App / Batch |
| :--- | :---: | :--- | :--- |
| `title` | Yes | Non-empty `string` | Shown in catalog table, batch banners, and ticket reports. |
| `risk_level` | Yes | `"read_only"` \| `"remediation"` | `"read_only"` scripts qualify for one-click **☑ Read-Only** (`Ctrl+Shift+O`) batch selection; `"remediation"` triggers UI confirmation gates. |
| `ps_edition` | Yes | `"Desktop"` \| `"Core"` | Use `"Desktop"` (`powershell.exe` 5.1) for maximum RMM & batch bundle compatibility. |
| `requires_admin` | Yes | `bool` | Triggers UAC elevation prompt; in batches, triggers a single consolidated **Run All Elevated** option. |
| `timeout_seconds` | Yes | Positive `int` (`> 0`) | Per-script `QTimer` timeout during local/batch `QProcess` runs. |
| `output_mode` | Yes | `"json"` \| `"text"` | Use `"json"` for structured UI grids, ticket tables, and rich batch reporting. |
| `params` | Yes | `list[dict]` (or `[]`) | Drives dynamic UI parameter inputs and in-memory RMM injection. |

### 3.2 Parameter Schema (`params`)
Each entry in `"params"` must match:
- `"name"`: Exact PowerShell variable name without `$` (e.g., `"MaxEvents"`).
- `"type"`: Must be one of `"string"`, `"int"`, or `"bool"` (switch `[switch]` parameters are **not** supported—use `[bool]`).
- `"default"`: Must match `"type"` (`"text"`, `10`, `true`/`false`).
- `"min"` / `"max"` *(optional, `"int"` only)*: Bounds enforced by the UI `QSpinBox`.

### 3.3 `param(...)` Injection Rules (`inject_parameters`)
[`ClipboardService.inject_parameters`](services/clipboard_service.py) parses and rewrites default values inside `param(...)` in memory using regex. To ensure injection never corrupts syntax:
1. Always include `[CmdletBinding()]` immediately above `param(...)`.
2. Give every parameter `[Parameter(Mandatory = $false)]`, an explicit type (`[string]`, `[int]`, `[bool]`), and a default value matching `.PSSTORE_META.params`.
3. **Place the closing `)` of `param(...)` on its own line** and **do not use nested parentheses** inside `param(...)` (e.g., do **not** use `[ValidateSet("A", "B")]` or `[ValidateRange(1, 10)]` inside `param(...)`). Validate string choices or clamp integer ranges **inside the `try { ... }` block** instead.
4. **Avoid commas inside string defaults** in `param(...)` (the default-value regex stops at commas).
5. Every declared parameter **MUST** be referenced in the script body after `$ErrorActionPreference = 'Stop'` (`tools/lint_scripts.py` rejects unused parameters).

---

## 4. Batch Scripting Contract (Bundles & Multi-Script Runs)

PowerShellStore supports two batch workflows when technicians check multiple scripts:
1. **Combined Clipboard Bundles** (`ClipboardService.combine_scripts_bundle`) — Wraps each checked script in an isolated PowerShell 5.1 scriptblock inside one standalone script:
   ```powershell
   try {
   & {
   <your script content>
   }
   }
   catch {
       Write-Error ('[ERROR] Script <Title> failed: ' + $_.Exception.Message)
   }
   ```
2. **Sequential Local & Single-UAC Batch Runs** (`ScriptRunner.execute_batch` / `execute_batch_elevated`) — Runs each checked script in order, logs an individual SQLite `run_history` record per script, and aggregates every script's `status`, `exit_code`, and `summary` into a consolidated **Batch Execution** evidence table.

To guarantee your script works cleanly inside both standalone runs and multi-script batches, obey **ALL 8 batch rules**:

| # | Batch Rule | Why It Matters |
| :---: | :--- | :--- |
| **1** | **NEVER call `exit` or `exit 1` inside `output_mode: "json"` scripts** *(especially never in `try` or `catch`)* | Inside a `& { ... }` bundle, `exit 1` terminates the **entire host PowerShell process** immediately—preventing `finally` from running and aborting every remaining script in the batch. Catch errors in `catch`, set `$status = "error"`, populate `$errors`, and let `finally` emit the JSON envelope naturally. *(Even in standalone runs, `ScriptRunner` inspects the JSON envelope's `status` field.)* |
| **2** | **NEVER use `#Requires` statements or `using namespace ...`** | PowerShell 5.1 rejects `#Requires` and `using` directives inside `& { ... }` scriptblocks with a parser error. Perform OS/module/edition checks conditionally in `try { ... }` (e.g., `Get-Command`). |
| **3** | **Zero global state pollution** | Never assign `$global:` variables, call persistent `Set-Location`/`cd`, leave `Set-StrictMode` enabled globally, or overwrite built-in automatic variables. Put helper functions inside the script (they stay scoped to `& { ... }` when bundled) and clean up any `$env:TEMP` files using unique random filenames inside `finally`. |
| **4** | **100% Non-Interactive** | Never call `Read-Host`, `Pause`, `Out-GridView`, interactive GUI popups, or blocking confirmation prompts (`-Confirm`). Pass `-Force` or `-Confirm:$false` where appropriate. |
| **5** | **No immediate restarts inside batch scripts** | Remediation scripts that support rebooting MUST default their reboot parameter to `$false` (`AutoReboot = $false` / `RebootIfRequired = $false`) and only schedule a delayed reboot (`shutdown.exe /r /t 60`) *after* emitting results so subsequent batch scripts can finish and logs reach the RMM. |
| **6** | **Honest `risk_level` classification** | Technicians use **☑ Read-Only** (`Ctrl+Shift+O`) to safely bulk-check diagnostics across all categories. A `"read_only"` script **MUST NOT** modify registry keys, files, services, caches, or system state (other than cleaning up its own temporary scratch files created in `$env:TEMP`). |
| **7** | **Accurate `requires_admin` flag** | `LauncherView` inspects all checked scripts before launching a batch and consolidates them into a single **Run All Elevated (UAC)** decision. Always set `"requires_admin": true` if any cmdlet requires elevation. |
| **8** | **Clear one-line `summary` and accurate `status`** | The Batch Execution results table displays one row per script (`Step`, `Script`, `Category`, `Status`, `ExitCode`, `DurationMs`, `Summary`). Ensure `$status` is `"pass"`, `"warning"`, `"fail"`, or `"error"` and `$summary` concisely states counts and outcomes. |

---

## 5. Dual-Purpose Output Contract (`Format-Table` + JSON Envelope)

When `"output_mode": "json"`, every script must follow the dual output structure so both RMM activity logs (ASCII table) and PowerShellStore's **Structured Results** / **Copy Ticket Report** tabs render cleanly:

1. **Human-Readable ASCII Table First:**
   ```powershell
   if ($results.Count -gt 0) {
       $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
       Write-Output $tableOutput.Trim()
       Write-Output ""
   }
   ```
2. **Flat PascalCase Objects in `data`:** Every item in `$results` MUST be a flat `[PSCustomObject]` with consistent PascalCase property names (e.g., `DeviceName`, `Status`, `LatencyMs`). Never nest objects or raw unparsed blocks inside `data`.
3. **Compressed Single-Line JSON Envelope Last (in `finally`):**
   ```powershell
   $payload = @{
       status  = $status   # "pass", "warning", "fail", or "error"
       summary = $summary  # Concise human-readable single-line outcome
       data    = @($results)
       errors  = @($errors) # Flat string array (NEVER use ,@($errors))
   }
   $payload | ConvertTo-Json -Depth 4 -Compress
   ```
4. **Suppress Stray Pipeline Output:** Pipe setup calls (`Add-Type`, `$list.Add(...)` if returning an index—actually `[System.Collections.Generic.List[PSObject]]::Add()` returns `void`, whereas `ArrayList.Add()` leaks integers to `stdout`!) and helper commands into `| Out-Null` so `stdout` stays clean and the JSON line remains parseable.

---

## 6. PowerShell 5.1 (`Desktop`) Compatibility & Error Handling

1. **Top-Level Strict Error Handling:**
   - Set `$ErrorActionPreference = 'Stop'` immediately after `param(...)`.
   - Wrap operational logic in `try { ... } catch { ... } finally { ... }`.
   - Pass `-ErrorAction Stop` explicitly to cmdlets inside `try` so non-terminating cmdlet errors trigger `catch`.
2. **PowerShell 5.1 Runtime Guardrails:**
   - **NEVER use `[Environment]::TickCount64`** (does not exist in .NET Framework 4.x used by Windows PowerShell 5.1; `tools/lint_scripts.py` explicitly rejects it).
   - **NEVER use PowerShell 7+ syntax:** No ternary `? :`, null-coalescing `??`, pipeline chain operators `&&` / `||`, or `ForEach-Object -Parallel`.
   - **Collections:** Use `[System.Collections.Generic.List[PSObject]]::new()` / `[System.Collections.Generic.List[string]]::new()` instead of `+=` array concatenation or `ArrayList`.
   - **Resilient Fallbacks:** When practical, guard optional/CIM-dependent cmdlets cleanly and fall back to `.NET`, Registry (`.OpenSubKey(..., $false)` read-only), or native CLI (`netsh`, `manage-bde`, `dsregcmd`) with graceful empty-state handling.
   - **Security:** Never hardcode credentials, API keys, tokens, or tenant secrets.

---

## 7. Ready-to-Copy Script Templates

### Template A — Batch-Safe Read-Only Diagnostic (`output_mode: "json"`)

```powershell
<#
.SYNOPSIS
    Inspects target Windows services and reports running state cleanly for standalone or batch diagnostics.
.PSSTORE_META
    {
        "title": "Audit Windows Service Health",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 20,
        "output_mode": "json",
        "params": [
            {"name": "ServiceFilter", "type": "string", "default": "Spooler"},
            {"name": "ExpectedState", "type": "string", "default": "Running"},
            {"name": "MaxResults", "type": "int", "default": 25, "min": 1, "max": 500},
            {"name": "FlagStoppedAsWarning", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ServiceFilter = "Spooler",

    [Parameter(Mandatory = $false)]
    [string]$ExpectedState = "Running",

    [Parameter(Mandatory = $false)]
    [int]$MaxResults = 25,

    [Parameter(Mandatory = $false)]
    [bool]$FlagStoppedAsWarning = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    # Validate string & numeric bounds inside try (never use ValidateSet/ValidateRange in param())
    if ($ExpectedState -notmatch '^(Running|Stopped)$') {
        $ExpectedState = "Running"
    }
    $MaxResults = [math]::Max(1, [math]::Min(500, $MaxResults))
    if ([string]::IsNullOrWhiteSpace($ServiceFilter)) {
        $ServiceFilter = "*"
    }

    $services = @(Get-Service -Name $ServiceFilter -ErrorAction Stop | Select-Object -First $MaxResults)
    $mismatchCount = 0

    foreach ($svc in $services) {
        $stateStr = [string]$svc.Status
        $healthy = ($stateStr -eq $ExpectedState)
        if (-not $healthy) {
            $mismatchCount++
        }

        $results.Add([PSCustomObject]@{
            ServiceName = [string]$svc.Name
            DisplayName = [string]$svc.DisplayName
            Status      = $stateStr
            StartType   = [string]$svc.StartType
            Healthy     = $healthy
        })
    }

    if ($results.Count -eq 0) {
        $status = "warning"
        $summary = "No services matched filter '$ServiceFilter'."
        Write-Output $summary
    }
    else {
        $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
        Write-Output $tableOutput.Trim()
        Write-Output ""

        if ($FlagStoppedAsWarning -and $mismatchCount -gt 0) {
            $status = "warning"
            $summary = "Audited $($results.Count) service(s): $mismatchCount did not match expected state '$ExpectedState'."
        }
        else {
            $status = "pass"
            $summary = "Audited $($results.Count) service(s): all checks passed."
        }
    }
}
catch {
    $status = "error"
    $summary = "Service audit failed: $($_.Exception.Message)"
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
```

### Template B — Batch-Safe Remediation Script (`risk_level: "remediation"`, `output_mode: "json"`)

```powershell
<#
.SYNOPSIS
    Performs a targeted administrative remediation action and logs structured evidence without terminating host batch execution.
.PSSTORE_META
    {
        "title": "Sample Batch-Safe Remediation",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 60,
        "output_mode": "json",
        "params": [
            {"name": "TargetService", "type": "string", "default": "W32Time"},
            {"name": "PerformRestart", "type": "bool", "default": true}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetService = "W32Time",

    [Parameter(Mandatory = $false)]
    [bool]$PerformRestart = $true
)

$ErrorActionPreference = 'Stop'

$status = "pass"
$summary = ""
$results = [System.Collections.Generic.List[PSObject]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    $svc = Get-Service -Name $TargetService -ErrorAction Stop

    if ($PerformRestart) {
        Restart-Service -Name $TargetService -Force -Confirm:$false -ErrorAction Stop
        $actionTaken = "Restarted"
    }
    else {
        $actionTaken = "Verified Only"
    }

    $svcAfter = Get-Service -Name $TargetService -ErrorAction Stop
    $results.Add([PSCustomObject]@{
        ServiceName = [string]$svcAfter.Name
        Action      = $actionTaken
        StatusAfter = [string]$svcAfter.Status
        StartType   = [string]$svcAfter.StartType
    })

    $tableOutput = $results | Format-Table -AutoSize | Out-String -Width 4096
    Write-Output $tableOutput.Trim()
    Write-Output ""

    $summary = "$actionTaken service '$($svcAfter.Name)' cleanly (Status: $($svcAfter.Status))."
}
catch {
    # Do NOT call 'exit 1' here so multi-script combined bundles continue cleanly
    $status = "error"
    $summary = "Remediation failed for '$TargetService': $($_.Exception.Message)"
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
```

---

## 8. End-to-End Authoring & Verification Checklist

Whenever adding or updating a `.ps1` script in PowerShellStore, run every check below before finishing:

1. **Place & Name File:** Save under the appropriate `scripts/<NN_Category>/<Verb-Noun>.ps1`.
2. **Validate Contract & PS 5.1 AST Syntax:**
   ```powershell
   python tools/lint_scripts.py
   ```
   Expected result: `0 failed`.
3. **Verify Multi-Script `& { ... }` Bundle Parsing:**
   Confirm your new script parses cleanly inside a wrapped `& { ... }` bundle using PowerShell 5.1:
   ```powershell
   python -c "from pathlib import Path; import subprocess; from services.clipboard_service import ClipboardService; cb = ClipboardService(); b = cb.get_combined_rmm_ready_scripts([('Sample Custom Diagnostic', '99_Custom/Sample-CustomDiagnostic.ps1', {}), ('My New Script', '99_Custom/My-NewScript.ps1', {})]); ps = '\$errs = \$null; \$toks = \$null; [System.Management.Automation.Language.Parser]::ParseInput([Console]::In.ReadToEnd(), [ref]\$toks, [ref]\$errs) | Out-Null; if (\$errs.Count -gt 0) { \$errs | ForEach-Object { \$_.Message }; exit 1 }'; r = subprocess.run(['powershell.exe', '-NoProfile', '-Command', ps], input=b, text=True, capture_output=True); print('Bundle AST rc =', r.returncode, r.stdout, r.stderr)"
   ```
4. **Update Catalog Documentation in `README.md`:**
   - Add the new script's filename, title, risk level, admin requirement, parameters/defaults, and explanation under `## 📦 Built-In Script Catalog` in `README.md`, and update category/total script counts in `README.md` (and in `tests/test_shortcuts.py::test_rules_and_readme_document_all_shortcuts_and_scripts` if adding a built-in catalog script).
5. **Run Automated Test Suite:**
   ```powershell
   python -m pytest tests/ -v
   ```
   Confirm `test_production_scripts_scan_and_indexing`, `test_production_scripts_parameter_injection`, `test_script_contract_linter`, `test_rules_and_readme_document_all_shortcuts_and_scripts`, and all batch tests pass.
6. **Live App Verification:** Press `F5` in PowerShellStore to sync, verify the UI parameter controls appear, test **Copy RMM-Ready Script**, and check the script together with at least one other script to verify **Copy RMM-Ready (2 Scripts)** and **Run 2 Checked Locally**.
