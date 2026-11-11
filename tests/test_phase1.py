from pathlib import Path
import pytest
from repositories.catalog_repo import CatalogRepo, ScriptRecord, RunHistoryRecord
from services.scanner import ScriptScanner


@pytest.fixture
def temp_store(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    repo = CatalogRepo(db_file)
    scanner = ScriptScanner(scripts_dir, repo)
    return repo, scanner, scripts_dir


def test_repo_init_and_crud(temp_store):
    repo, scanner, _ = temp_store

    script = ScriptRecord(
        relative_path="01_System/Test-Script.ps1",
        category="System",
        filename="Test-Script.ps1",
        title="Test System Script",
        synopsis="A test script for verifying database persistence.",
        risk_level="read_only",
        ps_edition="Desktop",
        requires_admin=False,
        timeout_seconds=45,
        output_mode="json",
        params=[{"name": "MaxCount", "type": "int", "default": 10}],
        sha256="abc123hash",
    )

    script_id = repo.upsert_script(script)
    assert script_id is not None

    fetched = repo.get_script_by_id(script_id)
    assert fetched is not None
    assert fetched.title == "Test System Script"
    assert fetched.params == [{"name": "MaxCount", "type": "int", "default": 10}]
    assert fetched.requires_admin is False

    # Check search and filtering
    scripts = repo.get_all_scripts(category="System")
    assert len(scripts) == 1
    assert scripts[0].filename == "Test-Script.ps1"

    # Log run history
    run = RunHistoryRecord(
        script_id=script_id,
        duration_ms=120,
        exit_code=0,
        status="pass",
        summary="Success test execution",
        raw_output='{"status": "pass"}',
        json_payload='{"status": "pass"}',
    )
    run_id = repo.log_run(run)
    assert run_id is not None

    history = repo.get_history_for_script(script_id)
    assert len(history) == 1
    assert history[0].status == "pass"


def test_scanner_sync_and_category_derivation(temp_store):
    repo, scanner, scripts_dir = temp_store

    # Create category folder and script file
    cat_dir = scripts_dir / "04_Printers_Devices"
    cat_dir.mkdir()
    sample_script = cat_dir / "Reset-PrintSpooler.ps1"
    sample_script.write_text(
        """<#
.SYNOPSIS
    Clears stuck print jobs and restarts the Print Spooler service.
.PSSTORE_META
    {
        "title": "Reset Print Spooler",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 30,
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
""",
        encoding="utf-8",
    )

    summary = scanner.sync_catalog()
    assert summary.total_found == 1
    assert summary.added == 1
    assert summary.updated == 0

    record = repo.get_script_by_path("04_Printers_Devices/Reset-PrintSpooler.ps1")
    assert record is not None
    assert record.category == "Printers_Devices"
    assert record.title == "Reset Print Spooler"
    assert record.risk_level == "remediation"
    assert record.requires_admin is True
    assert record.params[0]["name"] == "ClearQueueFiles"

    # Second sync without changes should be unchanged
    summary2 = scanner.sync_catalog()
    assert summary2.unchanged == 1
    assert summary2.added == 0
    assert summary2.updated == 0

    # Modify file
    sample_script.write_text(
        sample_script.read_text(encoding="utf-8") + "\n# Extra line",
        encoding="utf-8",
    )
    summary3 = scanner.sync_catalog()
    assert summary3.updated == 1
    assert summary3.added == 0

    # Delete file and ensure sync cleans up
    sample_script.unlink()
    summary4 = scanner.sync_catalog()
    assert summary4.deleted == 1
    assert repo.get_script_by_path("04_Printers_Devices/Reset-PrintSpooler.ps1") is None

