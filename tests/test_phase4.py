from pathlib import Path
from repositories.catalog_repo import CatalogRepo
from services.scanner import ScriptScanner
from services.clipboard_service import ClipboardService, inject_parameters


def test_production_scripts_scan_and_indexing():
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    db_file = Path(__file__).resolve().parent.parent / "data" / "powershell_store.db"

    repo = CatalogRepo(db_file)
    scanner = ScriptScanner(scripts_dir, repo)

    summary = scanner.sync_catalog()
    assert len(summary.errors) == 0, f"Errors encountered during scan: {summary.errors}"
    assert summary.total_found >= 7

    scripts = repo.get_all_scripts()
    assert len(scripts) >= 7

    # Verify every script has required metadata
    for script in scripts:
        assert script.title, f"Script {script.relative_path} missing title"
        assert script.category, f"Script {script.relative_path} missing category"
        assert script.risk_level in ("read_only", "remediation"), f"Script {script.relative_path} invalid risk: {script.risk_level}"
        assert script.ps_edition in ("Desktop", "Core"), f"Script {script.relative_path} invalid edition: {script.ps_edition}"
        assert script.timeout_seconds > 0, f"Script {script.relative_path} invalid timeout"
        assert script.sha256, f"Script {script.relative_path} missing SHA256"


def test_production_scripts_parameter_injection():
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    clipboard = ClipboardService(scripts_dir)

    # 1. Reset-PrintSpooler
    spooler_rmm = clipboard.get_rmm_ready_script(
        "04_Devices/Reset-PrintSpooler.ps1",
        {"ClearQueueFiles": False},
    )
    assert "$ClearQueueFiles = $false" in spooler_rmm

    # 2. DiskSpaceReport
    disk_rmm = clipboard.get_rmm_ready_script(
        "01_System/Get-DiskSpaceReport.ps1",
        {"LowSpaceThresholdPercent": 25},
    )
    assert "$LowSpaceThresholdPercent = 25" in disk_rmm

    # 3. Test-PortConnectivity
    port_rmm = clipboard.get_rmm_ready_script(
        "02_Network/Test-PortConnectivity.ps1",
        {"TargetHost": "google.com", "Port": 80, "TimeoutMs": 1500},
    )
    assert "$TargetHost = 'google.com'" in port_rmm
    assert "$Port = 80" in port_rmm
    assert "$TimeoutMs = 1500" in port_rmm

