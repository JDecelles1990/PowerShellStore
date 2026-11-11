from pathlib import Path
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView
import pytest
from repositories.catalog_repo import CatalogRepo, ScriptRecord
from services.scanner import ScriptScanner
from services.clipboard_service import ClipboardService
from services.runner import ScriptRunner, RunResult
from ui.launcher_view import LauncherView
from ui.parameter_form import ParameterFormWidget
from ui.catalog_table_view import CatalogTableView
from ui.console_view import ConsoleView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ui_layer_boundary_enforcement():
    """Verify that ui/ files NEVER import forbidden modules (sqlite3, subprocess, hashlib)."""
    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    forbidden = ["sqlite3", "subprocess", "hashlib"]

    for py_file in ui_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for bad in forbidden:
            assert not re.search(
                rf"\bimport\s+{bad}\b|\bfrom\s+{bad}\s+import\b", content
            ), f"Forbidden import '{bad}' found in {py_file.name} (violates architectural layer boundary)!"


def test_parameter_form_widget(qapp):
    form = ParameterFormWidget()
    sample_script = ScriptRecord(
        relative_path="test.ps1",
        category="Test",
        filename="test.ps1",
        title="Test Script",
        params=[
            {"name": "ServiceName", "type": "string", "default": "Spooler"},
            {"name": "Restart", "type": "bool", "default": True},
            {"name": "MaxRetries", "type": "int", "default": 5, "min": 1, "max": 20},
        ],
    )

    form.load_script(sample_script)
    values = form.get_parameter_values()

    assert values["ServiceName"] == "Spooler"
    assert values["Restart"] is True
    assert values["MaxRetries"] == 5

    # Modify string and re-read
    form._input_widgets["ServiceName"].setText("CustomService")
    updated = form.get_parameter_values()
    assert updated["ServiceName"] == "CustomService"

    # Reset
    form.reset_to_defaults()
    assert form.get_parameter_values()["ServiceName"] == "Spooler"


def test_catalog_table_view_columns_and_resizability(qapp):
    catalog = CatalogTableView()
    # Ensure Category and Edition columns are removed and 3 columns remain
    assert catalog.table.columnCount() == 3
    headers = [catalog.table.horizontalHeaderItem(i).text() for i in range(catalog.table.columnCount())]
    assert headers == ["Title", "Risk Level", "Admin"]
    assert "Category" not in headers
    assert "Edition" not in headers

    # Ensure title column stretches to fill pane while other columns are interactively resizable
    header = catalog.table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert catalog.table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_structured_results_table_resizability(qapp):
    console = ConsoleView()
    # Trigger display of structured results
    result = RunResult(
        script_id=1,
        duration_ms=50,
        exit_code=0,
        status="pass",
        summary="Test success",
        data=[{"ColA": "Val1", "ColB": "Val2"}],
        errors=[],
        raw_output="test",
    )
    console.display_run_result(result)

    # Ensure results table allows interactive column resizing
    data_header = console.data_table.horizontalHeader()
    assert data_header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert console.data_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_launcher_view_initialization_and_collapse(qapp, tmp_path):
    db_file = tmp_path / "test_launcher.db"
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    repo = CatalogRepo(db_file)
    scanner = ScriptScanner(scripts_dir, repo)
    clipboard = ClipboardService(scripts_dir)
    runner = ScriptRunner(scripts_dir, repo)

    window = LauncherView(
        repo=repo,
        scanner=scanner,
        clipboard_service=clipboard,
        runner=runner,
    )
    assert window is not None
    assert window.windowTitle().startswith("PowerShellStore")
    assert window.sidebar is not None
    assert window.catalog_view is not None
    assert window.param_form is not None
    assert window.console_view is not None

    # Test collapsible sidebar toggle state and button label
    assert window._sidebar_expanded is True
    assert window.catalog_view.toggle_sidebar_btn.text() == "◀ Sidebar"
    window.toggle_sidebar()
    assert window._sidebar_expanded is False
    assert window.catalog_view.toggle_sidebar_btn.text() == "▶ Sidebar"

    window.toggle_sidebar()
    assert window._sidebar_expanded is True
    assert window.catalog_view.toggle_sidebar_btn.text() == "◀ Sidebar"

    # Test opacity slider in right pane top right
    assert window.opacity_slider is not None
    assert window.opacity_slider.minimum() == 60
    assert window.opacity_slider.maximum() == 100
    assert window.opacity_slider.value() == 100

    # Adjust opacity to 75%
    window.opacity_slider.setValue(75)
    assert abs(window.windowOpacity() - 0.75) < 0.01
    assert window.opacity_label.text() == "75%"

    # Reset to 100%
    window.opacity_slider.setValue(100)
    assert abs(window.windowOpacity() - 1.0) < 0.01
    assert window.opacity_label.text() == "100%"
