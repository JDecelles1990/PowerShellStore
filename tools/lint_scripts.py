#!/usr/bin/env python3
"""
tools/lint_scripts.py — Static Contract Linter for PowerShellStore Scripts

Validates all .ps1 files in the scripts/ directory against the architectural
contract defined in RULES.md / GEMINI.md:
  1. Mandatory .SYNOPSIS and .PSSTORE_META comment block.
  2. Valid JSON in .PSSTORE_META with required fields:
     - title (str)
     - risk_level ('read_only' | 'remediation')
     - ps_edition ('Desktop' | 'Core')
     - requires_admin (bool)
     - timeout_seconds (int > 0)
     - output_mode ('json' | 'text')
     - params (list[dict])
  3. [CmdletBinding()] presence.
  4. param(...) block matching all declared .PSSTORE_META params.
  5. $ErrorActionPreference = 'Stop' presence.
  6. try / catch error handling block.
  7. ConvertTo-Json emission if output_mode == 'json'.
"""

from __future__ import annotations

import argparse
import json
import re
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


def lint_script(script_path: Path, scripts_dir: Path) -> LintResult:
    rel_path = script_path.relative_to(scripts_dir).as_posix()
    result = LintResult(relative_path=rel_path)

    try:
        content = script_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = script_path.read_text(encoding="utf-8-sig")
        except Exception as e:
            result.passed = False
            result.errors.append(f"Failed to read file: {e}")
            return result

    # 1. Synopsis Check
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

    # 4. Error Handling (try / catch)
    if not re.search(r"\btry\s*\{", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing 'try { ... }' operational block.")
    if not re.search(r"\bcatch\b", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("Missing 'catch { ... }' block.")

    # 5. Output Mode Verification
    if output_mode == "json" and not re.search(r"ConvertTo-Json", content, re.IGNORECASE):
        result.passed = False
        result.errors.append("output_mode is 'json' but script does not call 'ConvertTo-Json'.")

    # 6. Parameter Declarations Matching
    params_declared = meta.get("params", [])
    if isinstance(params_declared, list) and len(params_declared) > 0:
        param_match = PARAM_BLOCK_REGEX.search(content)
        if not param_match:
            result.passed = False
            result.errors.append("Script declares params in .PSSTORE_META but lacks a param(...) block.")
        else:
            param_block_code = param_match.group(1)
            for p in params_declared:
                p_name = p.get("name")
                if not p_name:
                    result.passed = False
                    result.errors.append("Anonymous parameter entry in .PSSTORE_META.")
                    continue

                # Check parameter name exists in param() block
                pattern = rf"\${re.escape(p_name)}\b"
                if not re.search(pattern, param_block_code, re.IGNORECASE):
                    result.passed = False
                    result.errors.append(f"Parameter '${p_name}' declared in meta is missing from param(...) block.")

    return result


def run_linter(scripts_dir: Path | None = None) -> list[LintResult]:
    root_dir = scripts_dir if scripts_dir else DEFAULT_SCRIPTS_DIR
    results: list[LintResult] = []

    for ps1_file in sorted(root_dir.rglob("*.ps1")):
        res = lint_script(ps1_file, root_dir)
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

