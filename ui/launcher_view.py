from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from repositories.catalog_repo import CatalogRepo, ScriptRecord
from services.clipboard_service import ClipboardService
from services.runner import RunResult, ScriptRunner, is_running_as_admin
from services.scanner import ScriptScanner
from ui.catalog_table_view import CatalogTableView
from ui.console_view import ConsoleView
from ui.parameter_form import ParameterFormWidget
from ui.sidebar_view import SidebarView

logger = logging.getLogger(__name__)


class LauncherView(QMainWindow):
    def __init__(
        self,
        repo: CatalogRepo | None = None,
        scanner: ScriptScanner | None = None,
        clipboard_service: ClipboardService | None = None,
        runner: ScriptRunner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PowerShellStore — IT Helpdesk & MSP Script Workstation")
        self.resize(1360, 840)

        # Services & Repositories
        self.repo = repo if repo is not None else CatalogRepo()
        self.scanner = scanner if scanner is not None else ScriptScanner(repo=self.repo)
        self.clipboard_service = (
            clipboard_service if clipboard_service is not None else ClipboardService()
        )
        self.runner = runner if runner is not None else ScriptRunner(repo=self.repo)

        self._current_script: ScriptRecord | None = None
        self._sidebar_expanded: bool = True

        self._init_ui()
        self._init_shortcuts()
        self._init_watcher()
        self._connect_signals()

        # Initial catalog sync
        self.sync_and_refresh()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # Main 3-Pane Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Left Pane: Sidebar (Collapsible)
        self.sidebar = SidebarView()
        self.splitter.addWidget(self.sidebar)

        # 2. Center Pane: Catalog Table
        self.catalog_view = CatalogTableView()
        self.splitter.addWidget(self.catalog_view)

        # 3. Right Pane: Workstation & Inspector
        self.inspector_frame = QFrame()
        self.inspector_frame.setObjectName("InspectorFrame")
        self._init_inspector_ui()
        self.splitter.addWidget(self.inspector_frame)

        # Proportions: 240px sidebar, 450px catalog, remaining for workstation
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)
        self.splitter.setSizes([240, 450, 670])
        root_layout.addWidget(self.splitter, 1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _init_shortcuts(self) -> None:
        # Ctrl+B toggles sidebar collapse/expand
        self.shortcut_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_sidebar.activated.connect(self.toggle_sidebar)

    def _init_inspector_ui(self) -> None:
        layout = QVBoxLayout(self.inspector_frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Top Header Bar: Script Title (left) & Opacity Slider (right)
        top_header_layout = QHBoxLayout()
        top_header_layout.setContentsMargins(0, 0, 0, 0)
        top_header_layout.setSpacing(12)

        self.script_title_label = QLabel("Select a Script")
        self.script_title_label.setObjectName("HeaderTitle")
        self.script_title_label.setWordWrap(True)
        top_header_layout.addWidget(self.script_title_label, 1)

        # Opacity Slider Container (at top right: 60% to 100%)
        opacity_container = QWidget()
        opacity_layout = QHBoxLayout(opacity_container)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(6)

        self.opacity_title = QLabel("Opacity:")
        self.opacity_title.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: 500;")
        opacity_layout.addWidget(self.opacity_title)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(60, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(80)
        self.opacity_slider.setToolTip("Adjust window opacity (60% - 100%)")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)

        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(32)
        self.opacity_label.setStyleSheet("color: #9ca3af; font-size: 11px; font-family: Consolas, monospace;")
        opacity_layout.addWidget(self.opacity_label)

        top_header_layout.addWidget(opacity_container)
        layout.addLayout(top_header_layout)

        # Chips / Badges Layout
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.category_chip = QLabel("Category")
        self.category_chip.setStyleSheet("background-color: #374151; color: #93c5fd; padding: 2px 8px; border-radius: 4px; font-weight: 500;")
        chips_layout.addWidget(self.category_chip)

        self.risk_chip = QLabel("READ-ONLY")
        self.risk_chip.setStyleSheet("background-color: #065f46; color: #34d399; padding: 2px 8px; border-radius: 4px; font-weight: 500;")
        chips_layout.addWidget(self.risk_chip)

        self.admin_chip = QLabel("ADMIN NOT REQUIRED")
        self.admin_chip.setStyleSheet("background-color: #374151; color: #9ca3af; padding: 2px 8px; border-radius: 4px;")
        chips_layout.addWidget(self.admin_chip)

        self.edition_chip = QLabel("Desktop 5.1")
        self.edition_chip.setStyleSheet("background-color: #374151; color: #9ca3af; padding: 2px 8px; border-radius: 4px;")
        chips_layout.addWidget(self.edition_chip)

        self.timeout_chip = QLabel("30s Timeout")
        self.timeout_chip.setStyleSheet("background-color: #374151; color: #9ca3af; padding: 2px 8px; border-radius: 4px;")
        chips_layout.addWidget(self.timeout_chip)

        chips_layout.addStretch()
        layout.addLayout(chips_layout)

        # Synopsis
        self.synopsis_label = QLabel("Select a script from the catalog to configure parameters and run or copy.")
        self.synopsis_label.setWordWrap(True)
        self.synopsis_label.setStyleSheet("color: #9ca3af; font-size: 12px; margin-top: 4px;")
        layout.addWidget(self.synopsis_label)

        # Parameter Form
        self.param_form = ParameterFormWidget()
        layout.addWidget(self.param_form)

        # Action Bar (Three core RMM/Local actions)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.copy_raw_btn = QPushButton("📋 Copy Raw Script")
        self.copy_raw_btn.setToolTip("Copies exact .ps1 file from disk to the Windows Clipboard")
        self.copy_raw_btn.clicked.connect(self._on_copy_raw_clicked)
        action_bar.addWidget(self.copy_raw_btn)

        self.copy_rmm_btn = QPushButton("⚡ Copy RMM-Ready Script")
        self.copy_rmm_btn.setObjectName("PrimaryButton")
        self.copy_rmm_btn.setToolTip("Injects custom UI parameter values into param() defaults and copies to clipboard")
        self.copy_rmm_btn.clicked.connect(self._on_copy_rmm_clicked)
        action_bar.addWidget(self.copy_rmm_btn)

        self.run_local_btn = QPushButton("▶ Test Locally on My PC")
        self.run_local_btn.setObjectName("SuccessButton")
        self.run_local_btn.setToolTip("Executes script in non-blocking test sandbox via QProcess")
        self.run_local_btn.clicked.connect(self._on_run_local_clicked)
        action_bar.addWidget(self.run_local_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("DangerButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.runner.stop_execution)
        action_bar.addWidget(self.stop_btn)

        layout.addLayout(action_bar)

        # Workstation Tabs (Results, Raw Console, Source Code, Run History)
        self.console_view = ConsoleView()
        layout.addWidget(self.console_view, 1)

    def _init_watcher(self) -> None:
        """Sets up live filesystem watching for automatic catalog reload."""
        self.watcher = QFileSystemWatcher(self)
        scripts_path = self.scanner.scripts_dir
        if scripts_path.exists():
            self.watcher.addPath(str(scripts_path.resolve()))
            for sub in scripts_path.glob("*/"):
                if sub.is_dir():
                    self.watcher.addPath(str(sub.resolve()))

        self.watcher.directoryChanged.connect(self._on_fs_changed)
        self.watcher.fileChanged.connect(self._on_fs_changed)

    def _on_fs_changed(self, path: str) -> None:
        logger.info("Filesystem change detected at %s. Syncing catalog...", path)
        self.sync_and_refresh(show_toast=False)

    def _connect_signals(self) -> None:
        # Sidebar & Filter signals
        self.sidebar.filter_changed.connect(self._on_filters_changed)
        self.sidebar.sync_requested.connect(self.sync_and_refresh)
        self.catalog_view.toggle_sidebar_requested.connect(self.toggle_sidebar)
        self.catalog_view.script_selected.connect(self._on_script_selected)

        # Runner signals
        self.runner.started.connect(self._on_run_started)
        self.runner.output_received.connect(self.console_view.append_raw_output)
        self.runner.finished.connect(self._on_run_finished)
        self.runner.error_occurred.connect(self._on_run_error)

    def toggle_sidebar(self) -> None:
        """Toggles sidebar visibility to expand workspace for the other two panes."""
        self._sidebar_expanded = not self._sidebar_expanded
        self.sidebar.setVisible(self._sidebar_expanded)
        self.catalog_view.set_sidebar_button_state(self._sidebar_expanded)
        state_msg = (
            "Sidebar expanded"
            if self._sidebar_expanded
            else "Sidebar collapsed (more space for catalog & workstation)"
        )
        self.status_bar.showMessage(state_msg, 2500)

    def _on_opacity_changed(self, value: int) -> None:
        """Adjusts the application window opacity from 60% to 100%."""
        self.setWindowOpacity(value / 100.0)
        self.opacity_label.setText(f"{value}%")

    def sync_and_refresh(self, show_toast: bool = True) -> None:
        summary = self.scanner.sync_catalog()
        categories = self.repo.get_categories_with_counts()
        total_scripts = sum(c["count"] for c in categories)

        self.sidebar.update_categories(categories, total_scripts)
        self._on_filters_changed(
            self.sidebar._current_category,
            self.sidebar.search_input.text(),
            self.sidebar.risk_combo.currentText(),
            self.sidebar.edition_combo.currentText(),
        )

        msg = f"Catalog synced: {total_scripts} script(s) loaded ({summary.added} added, {summary.updated} updated, {summary.deleted} removed)."
        if show_toast:
            self.status_bar.showMessage(msg, 5000)

    def _on_filters_changed(self, category: str, search: str, risk: str, edition: str) -> None:
        risk_filter = risk if risk not in ("All", "All Risks") else None
        edition_filter = edition if edition not in ("All", "All Editions") else None
        scripts = self.repo.get_all_scripts(
            category=category if category != "All" else None,
            search=search if search else None,
            risk_level=risk_filter,
            ps_edition=edition_filter,
        )
        self.catalog_view.set_scripts(scripts)

    def _on_script_selected(self, script: ScriptRecord) -> None:
        self._current_script = script
        self.script_title_label.setText(script.title)
        self.category_chip.setText(script.category)

        # Risk badge
        if script.risk_level == "remediation":
            self.risk_chip.setText("REMEDIATION")
            self.risk_chip.setStyleSheet("background-color: #78350f; color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-weight: bold;")
        else:
            self.risk_chip.setText("READ-ONLY")
            self.risk_chip.setStyleSheet("background-color: #065f46; color: #34d399; padding: 2px 8px; border-radius: 4px; font-weight: bold;")

        # Admin badge
        if script.requires_admin:
            self.admin_chip.setText("🛡️ REQUIRES ADMIN")
            self.admin_chip.setStyleSheet("background-color: #1e3a8a; color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-weight: 500;")
        else:
            self.admin_chip.setText("Standard User")
            self.admin_chip.setStyleSheet("background-color: #374151; color: #9ca3af; padding: 2px 8px; border-radius: 4px;")

        self.edition_chip.setText(f"PowerShell {script.ps_edition}")
        self.timeout_chip.setText(f"{script.timeout_seconds}s Timeout")

        self.synopsis_label.setText(script.synopsis or "No synopsis available.")

        # Load parameters form
        self.param_form.load_script(script)

        # Load Script Source Code into Preview tab
        try:
            raw_code = self.clipboard_service.get_raw_script(script.relative_path)
            self.console_view.set_script_source(raw_code)
        except Exception as e:
            self.console_view.set_script_source(f"# Error reading script source: {e}")

        # Load Run History
        if script.id:
            history = self.repo.get_history_for_script(script.id)
            self.console_view.display_history(history)

    def _on_copy_raw_clicked(self) -> None:
        if not self._current_script:
            return
        try:
            self.clipboard_service.copy_raw_script(self._current_script.relative_path)
            self.status_bar.showMessage("📋 Copied Raw Script to Windows Clipboard!", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Copy Failed", f"Failed to copy raw script: {e}")

    def _on_copy_rmm_clicked(self) -> None:
        if not self._current_script:
            return
        try:
            params = self.param_form.get_parameter_values()
            self.clipboard_service.copy_rmm_ready_script(
                self._current_script.relative_path, params
            )
            self.status_bar.showMessage("⚡ Copied RMM-Ready Script (with injected parameters) to Clipboard!", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Copy Failed", f"Failed to copy RMM-ready script: {e}")

    def _on_run_local_clicked(self) -> None:
        if not self._current_script:
            return

        # Remediation safety confirmation gate
        if self._current_script.risk_level == "remediation":
            confirm = QMessageBox.warning(
                self,
                "Remediation Script Confirmation",
                f"'{self._current_script.title}' is marked as REMEDIATION and will alter system state on this PC.\n\n"
                "Are you sure you want to test this script locally?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        # Elevation pre-flight check
        if self._current_script.requires_admin and not is_running_as_admin():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Administrator Privileges Required")
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setText(
                f"'{self._current_script.title}' requires Administrator privileges, but PowerShellStore is currently running un-elevated.\n\n"
                "How would you like to execute this test?"
            )
            elevated_btn = msg_box.addButton("🛡️ Run Elevated (UAC Prompt)", QMessageBox.ButtonRole.AcceptRole)
            unelevated_btn = msg_box.addButton("Run Un-elevated (May Fail)", QMessageBox.ButtonRole.ActionRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(elevated_btn)

            msg_box.exec()
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == cancel_btn:
                return
            elif clicked_btn == elevated_btn:
                params = self.param_form.get_parameter_values()
                self.runner.execute_script_elevated(self._current_script, params)
                self.status_bar.showMessage("Launched in elevated PowerShell session (UAC)", 5000)
                return

        params = self.param_form.get_parameter_values()
        self.console_view.clear_raw_output()
        self.runner.execute_script(self._current_script, params)

    def _on_run_started(self) -> None:
        self.status_bar.showMessage(f"Executing '{self._current_script.title if self._current_script else ''}'...")
        self.run_local_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_run_finished(self, result: RunResult) -> None:
        self.run_local_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.console_view.display_run_result(result)

        # Refresh history tab
        if self._current_script and self._current_script.id:
            history = self.repo.get_history_for_script(self._current_script.id)
            self.console_view.display_history(history)

        self.status_bar.showMessage(
            f"Execution finished with status '{result.status.upper()}' in {result.duration_ms} ms.",
            5000,
        )

    def _on_run_error(self, message: str) -> None:
        self.run_local_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Execution Error", message)
        self.status_bar.showMessage(f"Execution Error: {message}", 5000)
