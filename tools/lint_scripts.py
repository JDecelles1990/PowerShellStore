#!/usr/bin/env python3
"""
tools/lint_scripts.py — Static Contract Linter for PowerShellStore Scripts

Validates all .ps1 files in the scripts/ directory against the architectural
contract defined in RULES.md / GEMINI.md:
  1. Mandatory <# ... .SYNOPSIS ... .PSSTORE_META ... #> comment block at top.
  2. Valid JSON in .PSSTORE_META with required fields & parameter schema:
     - title (str)
     - risk_level ('read_only' | 'remediation')
     - ps_edition ('Desktop' | 'Core')
     - requires_admin (bool)
     - timeout_seconds (int > 0)
     - output_mode ('json' | 'text')
     - params (list[dict] with 'name', 'type', 'default')
  3. [CmdletBinding()] presence.
  4. param(...) block matching all declared .PSSTORE_META params, and params used in script body.
  5. $ErrorActionPreference = 'Stop' presence.
  6. try / catch / finally error handling blocks.
  7. Human-readable Format-Table output and ConvertTo-Json -Compress when output_mode == 'json'.
  8. PowerShell AST syntax validation (via powershell.exe / pwsh when available).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

META_REGEX = re.compile(r"\.PSSTORE_META\s*(\{.*?\})\s*#>", re.DOTALL | re.IGNORECASE)
PARAM_BLOCK_REGEX = re.compile(r"\bparam\s*\((.*?)\)\s*(?=\r?\n|$)", re.DOTALL | re.IGNORECASE)


@dataclass
class LintResult:
    relative_path: str
    title: str = "Unknown"
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_powershell_syntax_batch(ps1_files: list[Path]) -> dict[str, list[str]]:
    """Parses all .ps1 files in a single PowerShell invocation via AST Parser."""
    errors_by_path: dict[str, list[str]] = {}
    ps_exe = shutil.which("powershell.exe") or shutil.which("pwsh") or shutil.which("powershell")
    if not ps_exe or not ps1_files:
        return errors_by_path

    # Pass file paths over stdin or arguments to avoid command-line length limits
    ps_script = (
        "$input | ForEach-Object { "
        "$p = $_.Trim(); if (-not $p) { return }; "
        "$err = $null; $tok = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tok, [ref]$err) | Out-Null; "
        "if ($err.Count -gt 0) { "
        "$msgs = @($err | ForEach-Object { \"Line $($_.Extent.StartLineNumber): $($_.Message)\" }); "
        "@{ path = $p; errors = $msgs } | ConvertTo-Json -Compress "
        "} }"
    )
    stdin_payload = "\n".join(str(p.resolve()) for p in ps1_files)
    try:
        proc = subprocess.run(
            [ps_exe, "-NoProfile", "-Command", ps_script],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    entry = json.loads(line)
                    resolved = str(Path(entry["path"]).resolve())
                    errors_by_path[resolved] = entry.get("errors", [])
                except Exception:
                    pass
    except Exception:
        pass
    return errors_by_path


def lint_script(
    script_path: Path,
    scripts_dir: Path,
    syntax_errors: list[str] | None = None,
) -> LintResult:
    rel_path = script_path.relative_to(scripts_dir).as_posix()
    result = LintResult(relative_path=rel_path)

    if syntax_errors:
        result.passed = False
        for syn_err in syntax_errors:
            result.errors.append(f"PowerShell syntax error: {syn_err}")

    try:
        content = script_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = script_path.read_text(encoding="utf-8-sig")
        except Exception as e:
            result.passed = False
            result.errors.append(f"Failed to read file: {e}")
            return result

    # 1. Header Placement & Synopsis Check
    if not content.lstrip().startswith("<#"):
        result.passed = False
        result.errors.append("Script must begin with a <# ... #> help comment block.")

    if not re.search(r"\.SYNOPSIS", content, re.IGNORECASE):
        result.warnings.append("Missing .SYNOPSIS comment block.")

    # 2. .PSSTORE_META JSON Header Check
    match = META_REGEX.search(content)
    if not match:
        result.passed = False
        result.errors.append("Missing or unclosed <# ... .PSSTORE_META ... #> comment header.")
        return result

    raw_json = match.group(1).strip()
    try:
        meta = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        result.passed = False
        result.errors.append(f"Malformed JSON in .PSSTORE_META: {exc.msg} (line {exc.lineno})")
        return result

    # Validate Required Fields
    title = meta.get("title")
    if not title or not isinstance(title, str):
        result.passed = False
        result.errors.append("Missing or non-string 'title' in .PSSTORE_META.")
    else:
        result.title = title

    risk_level = meta.get("risk_level")
    if risk_level not in ("read_only", "remediation"):
        result.passed = False
        result.errors.append(f"Invalid 'risk_level': {risk_level} (must be 'read_only' or 'remediation').")

    ps_edition = meta.get("ps_edition")
    if ps_edition not in ("Desktop", "Core"):
        result.passed = False
        result.errors.append(f"Invalid 'ps_edition': {ps_edition} (must be 'Desktop' or 'Core').")

    requires_admin = meta.get("requires_admin")
    if not isinstance(requires_admin, bool):
        result.passed = False
        result.errors.append("'requires_admin' must be a boolean.")

    timeout_seconds = meta.get("timeout_seconds")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        result.passed = False
        result.errors.append("'timeout_seconds' must be a positive integer.")

    output_mode = meta.get("output_mode", "json")
    if output_mode not in ("json", "text"):
        result.passed = False
        result.errors.append(f"Invalid 'output_mode': {output_mode} (must be 'json' or 'text').")

    # 3. CmdletBinding & ErrorActionPreference
    if not re.search(r"\[\s*CmdletBinding\b", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing '[CmdletBinding()]' attribute.")

    if not re.search(r"\$ErrorActionPreference\s*=\s*['\"]Stop['\"]", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing '$ErrorActionPreference = 'Stop''.")

    # 4. Error Handling (try / catch / finally)
    if not re.search(r"\btry\s*\{", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing 'try { ... }' operational block.")
    if not re.search(r"\bcatch\b", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing 'catch { ... }' block.")
    if not re.search(r"\bfinally\s*\{", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing 'finally { ... }' block.")

    # 5. Output Mode Verification
    if output_mode == "json":
        if not re.search(r"ConvertTo-Json\s+-Depth\s+4\s+-Compress", content, re.IGNORECASE):
            result.passed = False
            result.errors.append("output_mode is 'json' but script does not emit 'ConvertTo-Json -Depth 4 -Compress'.")
        if not re.search(r"Format-Table", content, re.IGNORECASE):
            result.passed = False
            result.errors.append("output_mode is 'json' but script lacks 'Format-Table' human-readable output before JSON.")
        if re.search(r"\berrors\s*=\s*,@", content, re.IGNORECASE):
            result.passed = False
            result.errors.append("Nested array bug 'errors = ,@(...)' found; use 'errors = @(...)' instead.")

    # 6. PowerShell 5.1 (Desktop) Compatibility Guardrails
    if ps_edition == "Desktop":
        if "TickCount64" in content:
            result.passed = False
            result.errors.append("PS 5.1 incompatibility: '[Environment]::TickCount64' does not exist in .NET Framework 4.x.")

    # 7. Parameter Declarations Matching & Usage Check
    params_declared = meta.get("params", [])
    if not isinstance(params_declared, list):
        result.passed = False
        result.errors.append("'params' in .PSSTORE_META must be a list.")
    elif len(params_declared) > 0:
        param_match = PARAM_BLOCK_REGEX.search(content)
        if not param_match:
            result.passed = False
            result.errors.append("Script declares params in .PSSTORE_META but lacks a param(...) block.")
        else:
            param_block_code = param_match.group(1)
            body_after_pref = re.split(
                r"\$ErrorActionPreference\s*=\s*['\"]Stop['\"]", content, maxsplit=1
            )[-1]
            for p in params_declared:
                p_name = p.get("name")
                p_type = p.get("type")
                if not p_name:
                    result.passed = False
                    result.errors.append("Anonymous parameter entry in .PSSTORE_META.")
                    continue
                if p_type not in ("string", "int", "bool"):
                    result.passed = False
                    result.errors.append(f"Invalid parameter type '{p_type}' for '${p_name}'.")
                if "default" not in p:
                    result.passed = False
                    result.errors.append(f"Parameter '${p_name}' in .PSSTORE_META missing 'default' value.")

                pattern = rf"\${re.escape(p_name)}\b"
                if not re.search(pattern, param_block_code, re.IGNORECASE):
                    result.passed = False
                    result.errors.append(f"Parameter '${p_name}' declared in meta is missing from param(...) block.")
                if not re.search(pattern, body_after_pref, re.IGNORECASE):
                    result.passed = False
                    result.errors.append(f"Parameter '${p_name}' is declared but unused in script body.")

    return result


def run_linter(scripts_dir: Path | None = None) -> list[LintResult]:
    root_dir = scripts_dir if scripts_dir else DEFAULT_SCRIPTS_DIR
    ps1_files = sorted(root_dir.rglob("*.ps1"))
    syntax_map = check_powershell_syntax_batch(ps1_files)

    results: list[LintResult] = []
    for ps1_file in ps1_files:
        syn_errs = syntax_map.get(str(ps1_file.resolve()))
        res = lint_script(ps1_file, root_dir, syntax_errors=syn_errs)
        results.append(res)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint PowerShell scripts against PowerShellStore contract.")
    parser.add_argument("--dir", type=str, default=None, help="Directory containing PowerShell scripts.")
    args = parser.parse_args()

    target_dir = Path(args.dir) if args.dir else DEFAULT_SCRIPTS_DIR
    if not target_dir.exists():
        print(f"Error: Scripts directory not found at {target_dir}")
        return 2

    print(f"\n🔍 Linting PowerShell scripts in: {target_dir}\n" + "=" * 80)
    results = run_linter(target_dir)

    failed_count = 0
    for r in results:
        status_tag = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"{status_tag} | {r.relative_path:<45} | {r.title}")
        for err in r.errors:
            print(f"       🛑 Error: {err}")
        for warn in r.warnings:
            print(f"       ⚠️  Warning: {warn}")
        if not r.passed:
            failed_count += 1

    print("=" * 80)
    total = len(results)
    passed_count = total - failed_count
    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed.\n")

    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
