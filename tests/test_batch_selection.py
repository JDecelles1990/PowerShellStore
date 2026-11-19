from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QHeaderView, QMessageBox
import pytest

from repositories.catalog_repo import CatalogRepo, ScriptRecord
from services.clipboard_service import ClipboardService, combine_scripts_bundle
from services.hotkey_service import GlobalHotkeyManager
from services.runner import RunResult, ScriptRunner
from services.scanner import ScriptScanner
from services.startup_service import StartupService
from ui.catalog_table_view import CatalogTableView
from ui.launcher_view import LauncherView


SCRIPT_A = """<#
.SYNOPSIS
    First test script with string parameter.
.PSSTORE_META
    {
        "title": "Alpha Diagnostic",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": [
            {"name": "ServiceName", "type": "string", "default": "Spooler"}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ServiceName = "Spooler"
)
$ErrorActionPreference = 'Stop'
try {
    $res = @([PSCustomObject]@{ Service = $ServiceName; State = "OK" })
    Write-Output ($res | Format-Table -AutoSize | Out-String).Trim()
    $summary = "Checked $ServiceName"
    $status = "pass"
} catch {
    $status = "error"
    $summary = $_.Exception.Message
} finally {
    @{ status = $status; summary = $summary; data = @($res); errors = @() } | ConvertTo-Json -Depth 4 -Compress
}
"""

SCRIPT_B = """<#
.SYNOPSIS
    Second test script with int parameter.
.PSSTORE_META
    {
        "title": "Beta Threshold Check",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": [
            {"name": "Threshold", "type": "int", "default": 15, "min": 1, "max": 100}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$Threshold = 15
)
$ErrorActionPreference = 'Stop'
try {
    $res = @([PSCustomObject]@{ Threshold = $Threshold; Healthy = $true })
    Write-Output ($res | Format-Table -AutoSize | Out-String).Trim()
    $summary = "Threshold $Threshold verified"
    $status = "pass"
} catch {
    $status = "error"
    $summary = $_.Exception.Message
} finally {
    @{ status = $status; summary = $summary; data = @($res); errors = @() } | ConvertTo-Json -Depth 4 -Compress
}
"""

SCRIPT_C_REMEDIATION_ADMIN = """<#
.SYNOPSIS
    Third script requiring admin & remediation confirmation.
.PSSTORE_META
    {
        "title": "Gamma Admin Remediation",
        "risk_level": "remediation",
        "ps_edition": "Desktop",
        "requires_admin": true,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": []
    }
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
try {
    Write-Output "Remediation OK"
} catch {
    Write-Error $_.Exception.Message
} finally {
    @{ status = "pass"; summary = "Done"; data = @(); errors = @() } | ConvertTo-Json -Depth 4 -Compress
}
"""


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_combine_scripts_bundle_and_powershell_ast():
    # Empty & single-script passthrough
    assert combine_scripts_bundle([]) == ""
    assert combine_scripts_bundle([("One", "a.ps1", "Write-Output 1")]) == "Write-Output 1"

    # Real production scripts bundled together with custom parameters must parse cleanly in PS 5.1
    prod_dir = Path(__file__).resolve().parent.parent / "scripts"
    clipboard = ClipboardService(prod_dir)

    raw_bundle = clipboard.get_combined_raw_scripts(
        [
            ("Check Pending Reboot's Status", "01_System/Get-PendingRebootStatus.ps1"),
            ("Disk Free Space Report", "01_System/Get-DiskSpaceReport.ps1"),
            ("Get Microsoft Defender Status", "05_Security_Defender/Get-DefenderStatus.ps1"),
        ]
    )
    assert "Combined Multi-Script Bundle (3 scripts)" in raw_bundle
    assert "===== [1/3] Check Pending Reboot''s Status =====" in raw_bundle
    assert "& {" in raw_bundle

    rmm_bundle = clipboard.get_combined_rmm_ready_scripts(
        [
            ("Disk Free Space Report", "01_System/Get-DiskSpaceReport.ps1", {"LowSpaceThresholdPercent": 22}),
            ("Get Expiring & Expired Certificates", "05_Security_Defender/Get-ExpiringCertificates.ps1", {"DaysThreshold": 45}),
        ]
    )
    assert "[int]$LowSpaceThresholdPercent = 22" in rmm_bundle
    assert "[int]$DaysThreshold = 45" in rmm_bundle

    ps_ast_check = (
        "$errs = $null; $toks = $null; "
        "[System.Management.Automation.Language.Parser]::ParseInput([Console]::In.ReadToEnd(), [ref]$toks, [ref]$errs) | Out-Null; "
        "if ($errs.Count -gt 0) { $errs | ForEach-Object { $_.Message }; exit 1 }"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_ast_check],
        input=raw_bundle,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, f"PS 5.1 AST parse failed on raw_bundle: {proc.stdout} {proc.stderr}"

    proc_rmm = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_ast_check],
        input=rmm_bundle,
        text=True,
        capture_output=True,
    )
    assert proc_rmm.returncode == 0, f"PS 5.1 AST parse failed on rmm_bundle: {proc_rmm.stdout} {proc_rmm.stderr}"


def test_catalog_checkboxes_persist_across_filters_and_prune(qapp):
    catalog = CatalogTableView()
    assert catalog.table.columnCount() == 3
    headers = [catalog.table.horizontalHeaderItem(i).text() for i in range(3)]
    assert headers == ["Title", "Risk Level", "Admin"]
    assert catalog.table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch

    s1 = ScriptRecord(id=1, relative_path="01_System/A.ps1", category="System", filename="A.ps1", title="Alpha")
    s2 = ScriptRecord(id=2, relative_path="02_Network/B.ps1", category="Network", filename="B.ps1", title="Beta")

    changed_events: list[list[str]] = []
    catalog.checked_scripts_changed.connect(lambda items: changed_events.append([s.relative_path for s in items]))

    catalog.set_scripts([s1, s2])
    assert catalog.table.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert catalog.get_checked_count() == 0
    assert not catalog.clear_checked_btn.isEnabled()

    # Check row 0 via table item checkState (as user click does)
    catalog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert [s.relative_path for s in catalog.get_checked_scripts()] == ["01_System/A.ps1"]
    assert catalog.checked_badge.text() == "1 checked"
    assert catalog.clear_checked_btn.isEnabled()

    # Filter table to only s2 -> checked memory for s1 persists
    catalog.set_scripts([s2])
    assert catalog.table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert catalog.get_checked_count() == 1

    # Check visible s2 while filtered -> now 2 checked across categories
    catalog.check_all_visible()
    assert [s.relative_path for s in catalog.get_checked_scripts()] == ["01_System/A.ps1", "02_Network/B.ps1"]
    assert catalog.checked_badge.text() == "2 checked"

    # Re-filter back to [s1, s2] -> both boxes appear checked
    catalog.set_scripts([s1, s2])
    assert catalog.table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert catalog.table.item(1, 0).checkState() == Qt.CheckState.Checked

    # Prune missing script path
    catalog.prune_checked_scripts({"02_Network/B.ps1"})
    assert [s.relative_path for s in catalog.get_checked_scripts()] == ["02_Network/B.ps1"]

    # Clear all checked scripts
    catalog.clear_checked_scripts()
    assert catalog.get_checked_count() == 0
    assert catalog.checked_badge.text() == "0 checked"
    assert not catalog.clear_checked_btn.isEnabled()
    assert catalog.table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert catalog.table.item(1, 0).checkState() == Qt.CheckState.Unchecked
    assert len(changed_events) >= 3


def test_launcher_batch_selection_parameter_memory_and_copy(qapp, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "01_System").mkdir(parents=True)
    (scripts_dir / "02_Network").mkdir(parents=True)
    (scripts_dir / "01_System" / "Alpha.ps1").write_text(SCRIPT_A, encoding="utf-8")
    (scripts_dir / "02_Network" / "Beta.ps1").write_text(SCRIPT_B, encoding="utf-8")

    repo = CatalogRepo(tmp_path / "batch_ui.db")
    scanner = ScriptScanner(scripts_dir, repo)
    clipboard = ClipboardService(scripts_dir)
    runner = ScriptRunner(scripts_dir, repo)

    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = False
    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)

    window = LauncherView(
        repo=repo,
        scanner=scanner,
        clipboard_service=clipboard,
        runner=runner,
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )
    try:
        rows_by_title = {
            window.catalog_view.table.item(r, 0).text(): r
            for r in range(window.catalog_view.table.rowCount())
        }
        alpha_row = rows_by_title["Alpha Diagnostic"]
        beta_row = rows_by_title["Beta Threshold Check"]

        # Select Alpha & edit its parameter
        window.catalog_view.table.selectRow(alpha_row)
        assert window._current_script is not None
        assert window._current_script.title == "Alpha Diagnostic"
        window.param_form._input_widgets["ServiceName"].setText("WinRM")

        # Select Beta & edit its parameter
        window.catalog_view.table.selectRow(beta_row)
        assert window._current_script.title == "Beta Threshold Check"
        window.param_form._input_widgets["Threshold"].setValue(77)

        # Switching back restores edited value for Alpha
        window.catalog_view.table.selectRow(alpha_row)
        assert window.param_form.get_parameter_values()["ServiceName"] == "WinRM"

        # Check both scripts via shortcut Ctrl+Shift+A handler
        window._shortcut_check_all_visible()
        assert window.catalog_view.get_checked_count() == 2
        assert "2 Scripts" in window.copy_raw_btn.text()
        assert "2 Scripts" in window.copy_rmm_btn.text()
        assert "Run 2 Checked Locally" in window.run_local_btn.text()

        # Test Copy RMM-Ready bundle uses BOTH custom edited parameters
        captured: list[str] = []
        with patch.object(window.clipboard_service, "copy_to_clipboard", side_effect=lambda txt: captured.append(txt) or True):
            window._on_copy_rmm_clicked()
            window._on_copy_raw_clicked()

        assert len(captured) == 2
        rmm_out, raw_out = captured[0], captured[1]
        assert "[string]$ServiceName = 'WinRM'" in rmm_out
        assert "[int]$Threshold = 77" in rmm_out
        assert '[string]$ServiceName = "Spooler"' in raw_out
        assert "[int]$Threshold = 15" in raw_out

        # Clear checks resets dynamic button labels
        window._shortcut_clear_checked()
        assert window.copy_raw_btn.text() == "📋 Copy Raw Script"
        assert window.copy_rmm_btn.text() == "⚡ Copy RMM-Ready Script"
        assert window.run_local_btn.text() == "▶ Test Locally on My PC"
    finally:
        window._force_quit = True
        window.close()


def test_runner_execute_batch_sequential_and_history(qapp, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "01_System").mkdir(parents=True)
    (scripts_dir / "01_System" / "Alpha.ps1").write_text(SCRIPT_A, encoding="utf-8")
    (scripts_dir / "01_System" / "Beta.ps1").write_text(SCRIPT_B, encoding="utf-8")

    repo = CatalogRepo(tmp_path / "batch_run.db")
    scanner = ScriptScanner(scripts_dir, repo)
    scanner.sync_catalog()
    scripts = repo.get_all_scripts()
    assert len(scripts) == 2

    runner = ScriptRunner(scripts_dir, repo)
    progress_steps: list[tuple[int, int, str]] = []
    finished_results: list[RunResult] = []
    loop = QEventLoop()

    runner.batch_progress.connect(lambda step, total, sc: progress_steps.append((step, total, sc.title)))

    def _on_done(res: RunResult) -> None:
        finished_results.append(res)
        loop.quit()

    runner.batch_finished.connect(_on_done)
    QTimer.singleShot(25000, loop.quit)

    started = runner.execute_batch(
        [
            (scripts[0], {"ServiceName": "Spooler"}),
            (scripts[1], {"Threshold": 42}),
        ]
    )
    assert started is True
    assert runner.is_running is True
    loop.exec()

    assert len(finished_results) == 1, "Batch execution did not complete before timeout"
    res = finished_results[0]
    assert runner.is_running is False
    assert progress_steps == [
        (1, 2, "Alpha Diagnostic"),
        (2, 2, "Beta Threshold Check"),
    ]
    assert res.status == "pass"
    assert res.exit_code == 0
    assert res.script_category == "Batch"
    assert len(res.data) == 2
    assert res.data[0]["Step"] == "1/2"
    assert res.data[0]["Script"] == "Alpha Diagnostic"
    assert res.data[1]["Step"] == "2/2"
    assert res.data[1]["Summary"] == "Threshold 42 verified"

    # Each individual script run was persisted in SQLite run_history
    assert len(repo.get_history_for_script(scripts[0].id)) == 1
    assert len(repo.get_history_for_script(scripts[1].id)) == 1


def test_launcher_batch_remediation_gate_and_elevation_dialog(qapp, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "01_System").mkdir(parents=True)
    (scripts_dir / "01_System" / "Alpha.ps1").write_text(SCRIPT_A, encoding="utf-8")
    (scripts_dir / "01_System" / "Gamma.ps1").write_text(SCRIPT_C_REMEDIATION_ADMIN, encoding="utf-8")

    repo = CatalogRepo(tmp_path / "batch_gate.db")
    scanner = ScriptScanner(scripts_dir, repo)
    clipboard = ClipboardService(scripts_dir)
    runner = ScriptRunner(scripts_dir, repo)

    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = False
    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)

    window = LauncherView(
        repo=repo,
        scanner=scanner,
        clipboard_service=clipboard,
        runner=runner,
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )
    try:
        window.catalog_view.check_all_visible()
        assert window.catalog_view.get_checked_count() == 2

        # Rejecting consolidated remediation dialog must cancel execution
        with patch("ui.launcher_view.QMessageBox.warning", return_value=QMessageBox.StandardButton.No) as mock_warn, \
             patch.object(window.runner, "execute_batch") as mock_batch, \
             patch.object(window.runner, "execute_batch_elevated") as mock_elevated:
            window._on_run_local_clicked()
            mock_warn.assert_called_once()
            assert "Gamma Admin Remediation" in mock_warn.call_args[0][2]
            mock_batch.assert_not_called()
            mock_elevated.assert_not_called()

        # Accepting remediation + choosing Run All Elevated invokes execute_batch_elevated
        with patch("ui.launcher_view.is_running_as_admin", return_value=False), \
             patch("ui.launcher_view.QMessageBox.warning", return_value=QMessageBox.StandardButton.Yes), \
             patch("ui.launcher_view.QMessageBox") as mock_msg_cls, \
             patch.object(window.runner, "execute_batch_elevated", return_value=True) as mock_elevated:
            mock_box = MagicMock()
            elevated_btn = object()
            unelevated_btn = object()
            cancel_btn = object()
            mock_box.addButton.side_effect = [elevated_btn, unelevated_btn, cancel_btn]
            mock_box.clickedButton.return_value = elevated_btn
            mock_msg_cls.return_value = mock_box
            mock_msg_cls.StandardButton = QMessageBox.StandardButton
            mock_msg_cls.ButtonRole = QMessageBox.ButtonRole
            mock_msg_cls.Icon = QMessageBox.Icon
            mock_msg_cls.warning.return_value = QMessageBox.StandardButton.Yes

            window._on_run_local_clicked()
            mock_elevated.assert_called_once()
            passed_items = mock_elevated.call_args[0][0]
            assert len(passed_items) == 2
    finally:
        window._force_quit = True
        window.close()


def test_catalog_header_click_sorting_alphanumeric_risk_and_admin(qapp):
    catalog = CatalogTableView()
    assert catalog.table.horizontalHeader().sectionsClickable() is True

    scripts = [
        ScriptRecord(
            id=1,
            relative_path="01_System/check10.ps1",
            category="System",
            filename="check10.ps1",
            title="Check 10",
            risk_level="read_only",
            requires_admin=True,
        ),
        ScriptRecord(
            id=2,
            relative_path="01_System/check2.ps1",
            category="System",
            filename="check2.ps1",
            title="check 2",
            risk_level="remediation",
            requires_admin=False,
        ),
        ScriptRecord(
            id=3,
            relative_path="02_Network/alpha.ps1",
            category="Network",
            filename="alpha.ps1",
            title="Alpha Audit",
            risk_level="read_only",
            requires_admin=False,
        ),
        ScriptRecord(
            id=4,
            relative_path="04_Devices/beta.ps1",
            category="Devices",
            filename="beta.ps1",
            title="Beta Repair",
            risk_level="remediation",
            requires_admin=True,
        ),
    ]
    catalog.set_scripts(scripts)

    # Check one row and select a specific row ("check 2") before sorting
    catalog.set_script_checked("01_System/check10.ps1", True)
    catalog.table.selectRow(1)

    header = catalog.table.horizontalHeader()

    # Col 0: Title alphanumeric Ascending -> Descending
    header.sectionClicked.emit(0)
    titles_asc = [catalog.table.item(r, 0).text() for r in range(catalog.table.rowCount())]
    assert titles_asc == ["Alpha Audit", "Beta Repair", "check 2", "Check 10"]
    # Selection & checked state preserved after sort
    assert catalog.table.selectedItems()[0].text() == "check 2"
    check10_row = titles_asc.index("Check 10")
    assert catalog.table.item(check10_row, 0).checkState() == Qt.CheckState.Checked

    header.sectionClicked.emit(0)
    titles_desc = [catalog.table.item(r, 0).text() for r in range(catalog.table.rowCount())]
    assert titles_desc == ["Check 10", "check 2", "Beta Repair", "Alpha Audit"]

    # Col 1: Risk Level Ascending (READ-ONLY first) -> Descending (REMEDIATION first)
    header.sectionClicked.emit(1)
    risks_asc = [catalog.table.item(r, 1).text() for r in range(catalog.table.rowCount())]
    assert risks_asc == ["READ-ONLY", "READ-ONLY", "REMEDIATION", "REMEDIATION"]
    assert [catalog.table.item(r, 0).text() for r in range(2)] == ["Alpha Audit", "Check 10"]

    header.sectionClicked.emit(1)
    risks_desc = [catalog.table.item(r, 1).text() for r in range(catalog.table.rowCount())]
    assert risks_desc == ["REMEDIATION", "REMEDIATION", "READ-ONLY", "READ-ONLY"]

    # Col 2: Admin Ascending (No first) -> Descending (Yes first)
    header.sectionClicked.emit(2)
    admin_asc = [catalog.table.item(r, 2).text() for r in range(catalog.table.rowCount())]
    assert admin_asc == ["No", "No", "🛡️ Yes", "🛡️ Yes"]

    header.sectionClicked.emit(2)
    admin_desc = [catalog.table.item(r, 2).text() for r in range(catalog.table.rowCount())]
    assert admin_desc == ["🛡️ Yes", "🛡️ Yes", "No", "No"]

    # Re-populating catalog keeps active sort (Admin Descending)
    catalog.set_scripts(scripts)
    assert [catalog.table.item(r, 2).text() for r in range(catalog.table.rowCount())] == [
        "🛡️ Yes",
        "🛡️ Yes",
        "No",
        "No",
    ]


def test_catalog_check_read_only_button_and_shortcut(qapp, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "01_System").mkdir(parents=True)
    (scripts_dir / "01_System" / "Alpha.ps1").write_text(SCRIPT_A, encoding="utf-8")
    (scripts_dir / "01_System" / "Beta.ps1").write_text(SCRIPT_B, encoding="utf-8")
    (scripts_dir / "01_System" / "Gamma.ps1").write_text(SCRIPT_C_REMEDIATION_ADMIN, encoding="utf-8")

    repo = CatalogRepo(tmp_path / "ro_only.db")
    scanner = ScriptScanner(scripts_dir, repo)
    clipboard = ClipboardService(scripts_dir)
    runner = ScriptRunner(scripts_dir, repo)

    mock_startup = MagicMock(spec=StartupService)
    mock_startup.is_startup_enabled.return_value = False
    mock_hotkey = MagicMock(spec=GlobalHotkeyManager)

    window = LauncherView(
        repo=repo,
        scanner=scanner,
        clipboard_service=clipboard,
        runner=runner,
        startup_service=mock_startup,
        hotkey_manager=mock_hotkey,
    )
    try:
        # First check all 3 (including 1 remediation script)
        window.catalog_view.check_all_visible()
        assert window.catalog_view.get_checked_count() == 3

        # Click Read-Only button -> unchecks remediation, keeps only 2 read_only scripts
        window.catalog_view.check_readonly_btn.click()
        checked = window.catalog_view.get_checked_scripts()
        assert [s.title for s in checked] == ["Alpha Diagnostic", "Beta Threshold Check"]
        assert window.catalog_view.checked_badge.text() == "2 checked"
        assert "2 Scripts" in window.copy_rmm_btn.text()
        assert "Run 2 Checked Locally" in window.run_local_btn.text()

        # Clear then re-check via Ctrl+Shift+O shortcut
        window.catalog_view.clear_checked_scripts()
        assert window.catalog_view.get_checked_count() == 0
        window.shortcuts["check_read_only_visible"].activated.emit()
        assert [s.title for s in window.catalog_view.get_checked_scripts()] == [
            "Alpha Diagnostic",
            "Beta Threshold Check",
        ]
    finally:
        window._force_quit = True
        window.close()
