from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from PySide6.QtCore import QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication
import pytest

from repositories.catalog_repo import CatalogRepo
from services.clipboard_service import ClipboardService
from services.hotkey_service import GlobalHotkeyManager
from services.runner import RunResult, ScriptRunner
from services.scanner import ScriptScanner
from services.startup_service import StartupService
from ui.launcher_view import LauncherView


SAMPLE_SCRIPT = """<#
.SYNOPSIS
    Sample diagnostic script with parameters for shortcut testing.
.PSSTORE_META
    {
        "title": "Sample Shortcut Test Script",
        "risk_level": "read_only",
        "ps_edition": "Desktop",
        "requires_admin": false,
        "timeout_seconds": 15,
        "output_mode": "json",
        "params": [
            {"name": "TargetName", "type": "string", "default": "Spooler"},
            {"name": "MaxCount", "type": "int", "default": 10, "min": 1, "max": 100}
        ]
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$TargetName = "Spooler",

    [Parameter(Mandatory = $false)]
    [int]$MaxCount = 10
)
$ErrorActionPreference = 'Stop'
try {
    Write-Output "OK"
} catch {
    Write-Error $_.Exception.Message
} finally {
    @{ status = "pass"; summary = "OK"; data = @(); errors = @() } | ConvertTo-Json -Depth 4 -Compress
}
"""


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def launcher_window(qapp, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    cat_dir = scripts_dir / "01_System"
    cat_dir.mkdir(parents=True)
    (cat_dir / "Sample-Test.ps1").write_text(SAMPLE_SCRIPT, encoding="utf-8")

    db_file = tmp_path / "shortcuts_test.db"
    repo = CatalogRepo(db_file)
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
    yield window

    window._force_quit = True
    window.close()


def test_all_shortcuts_registered_without_duplicates(launcher_window: LauncherView):
    expected_shortcuts = {
        "toggle_sidebar",
        "open_scripts_folder",
        "focus_search",
        "sync_catalog",
        "escape_action",
        "check_all_visible",
        "check_read_only_visible",
        "clear_checked_scripts",
        "copy_raw_script",
        "copy_rmm_script",
        "run_local",
        "stop_execution",
        "reset_parameters",
        "tab_results",
        "tab_raw_console",
        "tab_script_source",
        "tab_run_history",
        "copy_ticket_report",
        "save_html_report",
        "clear_console",
        "opacity_increase",
        "opacity_decrease",
        "opacity_reset",
        "quit_app",
    }
    assert expected_shortcuts.issubset(set(launcher_window.shortcuts.keys()))
    assert launcher_window.shortcut_sidebar is launcher_window.shortcuts["toggle_sidebar"]

    seen_sequences: list[str] = []
    for name, shortcut in launcher_window.shortcuts.items():
        seqs = [QKeySequence(k).toString() for k in shortcut.keys()]
        assert seqs, f"Shortcut '{name}' must bind at least one key sequence"
        for seq in seqs:
            assert seq not in seen_sequences, f"Duplicate key sequence '{seq}' found on '{name}'"
            seen_sequences.append(seq)


def test_navigation_search_escape_and_tab_shortcuts(launcher_window: LauncherView):
    # Collapse sidebar, then invoke Ctrl+F handler -> expands sidebar & selects search text
    launcher_window.toggle_sidebar()
    assert launcher_window._sidebar_expanded is False
    launcher_window.sidebar.search_input.setText("Sample")

    launcher_window._focus_search_input()
    assert launcher_window._sidebar_expanded is True
    assert launcher_window.sidebar.search_input.selectedText() == "Sample"

    # Esc clears active search filter when no script is running
    launcher_window._handle_escape()
    assert launcher_window.sidebar.search_input.text() == ""

    # Esc stops active execution when runner is running
    with patch.object(type(launcher_window.runner), "is_running", new_callable=PropertyMock, return_value=True), \
         patch.object(launcher_window.runner, "stop_execution") as mock_stop:
        launcher_window._handle_escape()
        mock_stop.assert_called_once()

    # Ctrl+1..4 switch ConsoleView tabs
    for idx in (2, 1, 3, 0):
        launcher_window._switch_console_tab(idx)
        assert launcher_window.console_view.currentIndex() == idx


def test_script_action_param_reset_and_opacity_shortcuts(launcher_window: LauncherView):
    assert launcher_window._current_script is not None

    # Copy raw & RMM-ready script shortcuts (Ctrl+Shift+C / Ctrl+Shift+R)
    with patch.object(launcher_window.clipboard_service, "copy_raw_script") as mock_raw, \
         patch.object(launcher_window.clipboard_service, "copy_rmm_ready_script") as mock_rmm:
        launcher_window.shortcuts["copy_raw_script"].activated.emit()
        mock_raw.assert_called_once_with(launcher_window._current_script.relative_path)

        launcher_window.shortcuts["copy_rmm_script"].activated.emit()
        mock_rmm.assert_called_once_with(
            launcher_window._current_script.relative_path,
            launcher_window.param_form.get_parameter_values(),
        )

    # Parameter reset shortcut (Ctrl+Alt+R)
    launcher_window.param_form._input_widgets["TargetName"].setText("ModifiedValue")
    assert launcher_window.param_form.get_parameter_values()["TargetName"] == "ModifiedValue"
    launcher_window._shortcut_reset_parameters()
    assert launcher_window.param_form.get_parameter_values()["TargetName"] == "Spooler"

    # Run local shortcut (Ctrl+Enter) respects running guard
    with patch.object(launcher_window, "_on_run_local_clicked") as mock_run:
        with patch.object(type(launcher_window.runner), "is_running", new_callable=PropertyMock, return_value=True):
            launcher_window._shortcut_run_local()
            mock_run.assert_not_called()

        with patch.object(type(launcher_window.runner), "is_running", new_callable=PropertyMock, return_value=False):
            launcher_window._shortcut_run_local()
            mock_run.assert_called_once()

    # Stop shortcut (Shift+F5) triggers stop only while running
    with patch.object(launcher_window.runner, "stop_execution") as mock_stop:
        with patch.object(type(launcher_window.runner), "is_running", new_callable=PropertyMock, return_value=False):
            launcher_window._shortcut_stop_execution()
            mock_stop.assert_not_called()

        with patch.object(type(launcher_window.runner), "is_running", new_callable=PropertyMock, return_value=True):
            launcher_window._shortcut_stop_execution()
            mock_stop.assert_called_once()

    # Opacity step & clamp shortcuts (Ctrl+=, Ctrl+-, Ctrl+0)
    assert launcher_window.opacity_slider.value() == 100
    launcher_window._adjust_opacity(-5)
    assert launcher_window.opacity_slider.value() == 95
    launcher_window._adjust_opacity(-100)
    assert launcher_window.opacity_slider.value() == 60
    launcher_window._adjust_opacity(100)
    assert launcher_window.opacity_slider.value() == 100
    launcher_window._adjust_opacity(-20)
    assert launcher_window.opacity_slider.value() == 80
    launcher_window._reset_opacity()
    assert launcher_window.opacity_slider.value() == 100

    # Quit shortcut (Ctrl+Q) invokes quit_application cleanly
    with patch("ui.launcher_view.QApplication.instance") as mock_app_inst:
        mock_app = MagicMock()
        mock_app_inst.return_value = mock_app
        launcher_window.shortcuts["quit_app"].activated.emit()
        assert launcher_window._force_quit is True
        mock_app.quit.assert_called_once()


def test_console_clear_and_report_shortcuts(launcher_window: LauncherView):
    # Clear Raw Console shortcut (Ctrl+L)
    launcher_window.console_view.append_raw_output("Sample console line\n")
    assert "Sample console line" in launcher_window.console_view.raw_console.toPlainText()
    launcher_window._shortcut_clear_console()
    assert launcher_window.console_view.raw_console.toPlainText() == ""

    # Before any result is loaded, report shortcuts safely no-op
    with patch.object(launcher_window.console_view, "_on_copy_report_clicked") as mock_copy, \
         patch.object(launcher_window.console_view, "_on_save_report_clicked") as mock_save:
        launcher_window._shortcut_copy_report()
        launcher_window._shortcut_save_report()
        mock_copy.assert_not_called()
        mock_save.assert_not_called()

    # After loading a RunResult, Ctrl+Shift+T and Ctrl+S trigger report actions
    sample_result = RunResult(
        script_id=1,
        duration_ms=25,
        exit_code=0,
        status="pass",
        summary="Completed cleanly.",
        data=[{"Key": "Value"}],
        errors=[],
        raw_output="OK",
        script_title="Sample Shortcut Test Script",
        script_category="System",
    )
    launcher_window.console_view.display_run_result(sample_result)

    with patch.object(launcher_window.console_view, "_on_copy_report_clicked") as mock_copy, \
         patch.object(launcher_window.console_view, "_on_save_report_clicked") as mock_save:
        launcher_window._shortcut_copy_report()
        launcher_window._shortcut_save_report()
        mock_copy.assert_called_once()
        mock_save.assert_called_once()


def test_ui_tooltips_advertise_shortcuts(launcher_window: LauncherView):
    assert "Ctrl+Shift+C" in launcher_window.copy_raw_btn.toolTip()
    assert "Ctrl+Shift+R" in launcher_window.copy_rmm_btn.toolTip()
    assert "Ctrl+Enter" in launcher_window.run_local_btn.toolTip()
    assert "Shift+F5" in launcher_window.stop_btn.toolTip()
    assert "Ctrl+=" in launcher_window.opacity_slider.toolTip()
    assert "Ctrl+B" in launcher_window.catalog_view.toggle_sidebar_btn.toolTip()
    assert "Ctrl+O" in launcher_window.catalog_view.open_folder_btn.toolTip()
    assert "Ctrl+Shift+A" in launcher_window.catalog_view.check_all_btn.toolTip()
    assert "Ctrl+Shift+O" in launcher_window.catalog_view.check_readonly_btn.toolTip()
    assert "Ctrl+Shift+D" in launcher_window.catalog_view.clear_checked_btn.toolTip()
    assert "Ctrl+F" in launcher_window.sidebar.search_input.placeholderText()
    assert "F5" in launcher_window.sidebar.sync_button.toolTip()
    assert "Ctrl+Alt+R" in launcher_window.param_form.reset_btn.toolTip()
    assert "Ctrl+Shift+T" in launcher_window.console_view.copy_report_btn.toolTip()
    assert "Ctrl+S" in launcher_window.console_view.save_report_btn.toolTip()
    assert "Ctrl+L" in launcher_window.console_view.clear_console_btn.toolTip()
    for i in range(4):
        assert f"Ctrl+{i + 1}" in launcher_window.console_view.tabToolTip(i)


def test_rules_and_readme_document_all_shortcuts_and_scripts():
    root = Path(__file__).resolve().parent.parent
    gemini_text = (root / "GEMINI.md").read_text(encoding="utf-8")
    rules_text = (root / "RULES.md").read_text(encoding="utf-8")
    readme_text = (root / "README.md").read_text(encoding="utf-8")

    # Verify GEMINI.md and RULES.md enforce documenting shortcuts in README.md
    for doc_name, doc_text in (("GEMINI.md", gemini_text), ("RULES.md", rules_text)):
        assert "Keyboard Shortcuts Documentation Rule" in doc_text, f"{doc_name} missing rule header"
        assert "README.md" in doc_text, f"{doc_name} must reference README.md"

    # Verify README.md contains Keyboard Shortcuts section and all shortcut strings
    assert "## ⌨️ Keyboard Shortcuts" in readme_text
    required_shortcuts = [
        "Win+F8",
        "Ctrl+B",
        "Ctrl+O",
        "Ctrl+F",
        "F5",
        "Esc",
        "Ctrl+Shift+A",
        "Ctrl+Shift+O",
        "Ctrl+Shift+D",
        "Ctrl+Shift+C",
        "Ctrl+Shift+R",
        "Ctrl+Enter",
        "Ctrl+Return",
        "Shift+F5",
        "Ctrl+Alt+R",
        "Ctrl+1",
        "Ctrl+2",
        "Ctrl+3",
        "Ctrl+4",
        "Ctrl+Shift+T",
        "Ctrl+S",
        "Ctrl+L",
        "Ctrl+=",
        "Ctrl++",
        "Ctrl+-",
        "Ctrl+0",
        "Ctrl+Q",
    ]
    for shortcut_str in required_shortcuts:
        assert shortcut_str in readme_text, f"Shortcut '{shortcut_str}' missing from README.md"

    # Verify every .ps1 script file under scripts/ is documented in README.md
    ps1_files = sorted((root / "scripts").rglob("*.ps1"))
    assert len(ps1_files) == 38
    for ps1_path in ps1_files:
        assert ps1_path.name in readme_text, f"Script '{ps1_path.name}' missing from README.md"


def test_open_scripts_folder_button_and_shortcut(launcher_window: LauncherView):
    expected_url = QUrl.fromLocalFile(str(launcher_window.scanner.scripts_dir.resolve()))

    with patch("ui.launcher_view.QDesktopServices.openUrl", return_value=True) as mock_open:
        launcher_window.catalog_view.open_folder_btn.click()
        mock_open.assert_called_once_with(expected_url)

        mock_open.reset_mock()
        launcher_window.shortcuts["open_scripts_folder"].activated.emit()
        mock_open.assert_called_once_with(expected_url)

    with patch("ui.launcher_view.QDesktopServices.openUrl", return_value=False), \
         patch("ui.launcher_view.QMessageBox.warning") as mock_warn:
        launcher_window.open_scripts_folder()
        mock_warn.assert_called_once()
