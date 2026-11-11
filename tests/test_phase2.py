from pathlib import Path
from PySide6.QtCore import QCoreApplication
import pytest
from services.clipboard_service import (
    format_powershell_literal,
    inject_parameters,
    ClipboardService,
)
from services.runner import (
    build_powershell_args,
    ScriptRunner,
    RunResult,
)
from repositories.catalog_repo import CatalogRepo, ScriptRecord


def test_format_powershell_literal():
    assert format_powershell_literal(True) == "$true"
    assert format_powershell_literal(False) == "$false"
    assert format_powershell_literal(42) == "42"
    assert format_powershell_literal("Spooler") == "'Spooler'"
    assert format_powershell_literal("O'Connor") == "'O''Connor'"
    assert format_powershell_literal(["A", "B"]) == "@('A', 'B')"


def test_inject_parameters():
    script = """<#
.SYNOPSIS
    Reset Print Spooler
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [bool]$ClearQueueFiles = $true,
    [string]$TargetService = "Spooler",
    [int]$MaxRetries = 3
)

$ErrorActionPreference = 'Stop'
"""

    injected = inject_parameters(
        script,
        {
            "ClearQueueFiles": False,
            "TargetService": "CustomSpooler",
            "MaxRetries": 10,
        },
    )

    assert "$ClearQueueFiles = $false" in injected
    assert "$TargetService = 'CustomSpooler'" in injected
    assert "$MaxRetries = 10" in injected
    assert "[CmdletBinding()]" in injected
    assert ".SYNOPSIS" in injected


def test_build_powershell_args():
    args = build_powershell_args(
        {
            "ClearQueueFiles": False,
            "TargetService": "Spooler",
            "MaxCount": 50,
        }
    )
    assert "-ClearQueueFiles:$false" in args
    assert "-TargetService" in args
    assert any("Spooler" in a for a in args)
    assert "-MaxCount" in args
    assert "50" in args


def test_runner_envelope_parser():
    repo = CatalogRepo(":memory:")
    runner = ScriptRunner(repo=repo)
    runner._current_script = ScriptRecord(
        id=1,
        relative_path="test.ps1",
        category="Test",
        filename="test.ps1",
        title="Test",
        sha256="123",
    )

    # 1. JSON Envelope
    json_stdout = '{"status": "pass", "summary": "All tests passed", "data": [{"id": 1}], "errors": []}'
    res = runner._parse_results(0, json_stdout, "", 150)
    assert res.status == "pass"
    assert res.summary == "All tests passed"
    assert len(res.data) == 1

    # 2. Text RMM Output
    text_stdout = "[SUCCESS] Service restarted successfully.\nState: Running"
    res2 = runner._parse_results(0, text_stdout, "", 200)
    assert res2.status == "pass"
    assert "[SUCCESS]" in res2.summary

    # 3. Text Error Output
    err_stdout = "[ERROR] Access is denied."
    res3 = runner._parse_results(1, err_stdout, "Command failed", 100)
    assert res3.status == "error"
    assert "[ERROR]" in res3.summary

