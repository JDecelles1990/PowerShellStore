---
name: powershell-script-authoring
description: >-
  Author, update, or audit Windows PowerShell 5.1 scripts for PowerShellStore
  following the .PSSTORE_META schema, dual table/JSON output contract, and
  multi-script batch execution & bundling rules. Use whenever creating new .ps1
  scripts under scripts/ or checking batch compatibility.
---

# PowerShellStore Script & Batch Authoring Skill

Follow this workflow whenever creating, updating, or auditing any `.ps1` script under `scripts/`.

For complete field tables, ready-to-copy Read-Only and Remediation templates, and all PowerShell 5.1 / batch guardrails, read [`../../../SKILLS.md`](../../../SKILLS.md) first.

## Required Authoring Steps

1. **Choose Category & Path:**
   Place `<Verb-Noun>.ps1` (UTF-8, no BOM) inside the matching folder under `scripts/` (`01_System`, `02_Network`, `03_M365`, `04_Devices`, `05_Security_Defender`, or `99_Custom`).

2. **Follow `.PSSTORE_META` & `param(...)` Rules:**
   - Start at line 1 with `<#`, include `.SYNOPSIS` and valid `.PSSTORE_META` JSON (`title`, `risk_level`, `ps_edition`, `requires_admin`, `timeout_seconds`, `output_mode`, `params`).
   - Add `[CmdletBinding()]`, `[Parameter(Mandatory = $false)]`, explicit `[string]` / `[int]` / `[bool]` parameters matching `.PSSTORE_META.params`, closing `)` on its own line, no nested parentheses (`ValidateSet`/`ValidateRange`) inside `param(...)`, and no commas in defaults.
   - Reference every declared parameter after `$ErrorActionPreference = 'Stop'`.

3. **Enforce Batch Compatibility Contract:**
   - **No raw `exit` / `exit 1`** in JSON/batch-compatible scripts (killing the host process aborts remaining scripts inside `& { ... }` clipboard bundles). Report errors via `$status = "error"` and `$errors` so `finally` emits JSON cleanly.
   - **No `#Requires` or `using namespace`** (invalid inside `& { ... }` scriptblocks in Windows PowerShell 5.1).
   - **No global state leaks, interactive prompts, or unrequested immediate reboots** (use randomized `$env:TEMP` paths cleaned in `finally`, keep `"read_only"` strictly non-mutating for `Ctrl+Shift+O` bulk selection, and set `"requires_admin"` accurately for single-UAC batch elevation).
   - **No PS 7-only features or `[Environment]::TickCount64`**.

4. **Emit Dual Table + JSON Envelope:**
   - Write `Format-Table -AutoSize | Out-String -Width 4096` to `stdout` first.
   - End with flat PascalCase `[PSCustomObject]` entries inside `@{ status; summary; data = @($results); errors = @($errors) } | ConvertTo-Json -Depth 4 -Compress` in `finally`.

5. **Document & Verify:**
   - Document any newly added built-in script in `README.md` (and keep script counts synced in `README.md` and `tests/test_shortcuts.py`).
   - Run static + PS 5.1 AST validation and full test verification:
     ```powershell
     python tools/lint_scripts.py
     python -m pytest tests/ -v
     ```
