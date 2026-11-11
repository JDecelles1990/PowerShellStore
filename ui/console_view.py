from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repositories.catalog_repo import RunHistoryRecord
from services.report_service import ReportService
from services.runner import RunResult


class ConsoleView(QTabWidget):
    status_message_requested = Signal(str, int)

    def __init__(
        self,
        report_service: ReportService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.report_service = report_service if report_service is not None else ReportService()
        self._current_result: RunResult | None = None
        self._current_script_title: str = ""
        self._current_script_category: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        # Tab 1: Structured Results
        self.results_tab = QWidget()
        self._init_results_tab()
        self.addTab(self.results_tab, "Structured Results")

        # Tab 2: Raw Console
        self.raw_tab = QWidget()
        self._init_raw_tab()
        self.addTab(self.raw_tab, "Raw Console")

        # Tab 3: Script Source Code
        self.code_tab = QWidget()
        self._init_code_tab()
        self.addTab(self.code_tab, "Script Source")

        # Tab 4: Execution History
        self.history_tab = QWidget()
        self._init_history_tab()
        self.addTab(self.history_tab, "Run History")

    def _init_results_tab(self) -> None:
        layout = QVBoxLayout(self.results_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Status & Metrics Bar
        metrics_bar = QHBoxLayout()
        self.status_badge = QLabel("IDLE")
        self.status_badge.setStyleSheet(
            "background-color: #374151; color: #9ca3af; padding: 4px 12px; "
            "border-radius: 4px; font-weight: bold; font-size: 12px;"
        )
        metrics_bar.addWidget(self.status_badge)

        self.duration_label = QLabel("Duration: --")
        self.duration_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        metrics_bar.addWidget(self.duration_label)

        self.exit_code_label = QLabel("Exit Code: --")
        self.exit_code_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        metrics_bar.addWidget(self.exit_code_label)
        metrics_bar.addStretch()

        # Ticket Reporting Action Buttons
        self.copy_report_btn = QPushButton("📋 Copy Ticket Report")
        self.copy_report_btn.setObjectName("ReportButton")
        self.copy_report_btn.setToolTip(
            "Copies formatted rich-text ticket report with audit header and structured evidence to Windows Clipboard"
        )
        self.copy_report_btn.setEnabled(False)
        self.copy_report_btn.clicked.connect(self._on_copy_report_clicked)
        metrics_bar.addWidget(self.copy_report_btn)

        self.save_report_btn = QPushButton("💾 Save Report...")
        self.save_report_btn.setObjectName("ReportButton")
        self.save_report_btn.setToolTip("Exports self-contained HTML audit report to disk")
        self.save_report_btn.setEnabled(False)
        self.save_report_btn.clicked.connect(self._on_save_report_clicked)
        metrics_bar.addWidget(self.save_report_btn)

        layout.addLayout(metrics_bar)

        # Summary Box
        self.summary_box = QLabel("Run a script locally to view structured execution results.")
        self.summary_box.setWordWrap(True)
        self.summary_box.setStyleSheet(
            "background-color: #1f2937; border-left: 4px solid #3b82f6; "
            "padding: 10px; border-radius: 4px; color: #f3f4f6;"
        )
        layout.addWidget(self.summary_box)

        # Data Table — Resizable columns with horizontal scroll
        data_title = QLabel("STRUCTURED DATA / EVIDENCE")
        data_title.setObjectName("SectionTitle")
        layout.addWidget(data_title)

        self.data_table = QTableWidget()
        self.data_table.setColumnCount(0)
        h_header = self.data_table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_header.setStretchLastSection(False)
        h_header.setCascadingSectionResizes(True)
        self.data_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.data_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.data_table, 1)

        # Errors Box
        self.errors_label = QLabel("ERRORS & WARNINGS")
        self.errors_label.setObjectName("SectionTitle")
        self.errors_label.setVisible(False)
        layout.addWidget(self.errors_label)

        self.errors_box = QPlainTextEdit()
        self.errors_box.setReadOnly(True)
        self.errors_box.setMaximumHeight(80)
        self.errors_box.setStyleSheet(
            "background-color: #450a0a; border: 1px solid #7f1d1d; "
            "color: #fca5a5; font-family: Consolas, monospace;"
        )
        self.errors_box.setVisible(False)
        layout.addWidget(self.errors_box)

    def _init_raw_tab(self) -> None:
        layout = QVBoxLayout(self.raw_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        clear_btn = QPushButton("Clear Console")
        clear_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        clear_btn.clicked.connect(self.clear_raw_output)
        toolbar.addWidget(clear_btn)
        layout.addLayout(toolbar)

        self.raw_console = QPlainTextEdit()
        self.raw_console.setObjectName("ConsoleView")
        self.raw_console.setReadOnly(True)
        layout.addWidget(self.raw_console, 1)

    def _init_code_tab(self) -> None:
        layout = QVBoxLayout(self.code_tab)
        layout.setContentsMargins(12, 12, 12, 12)

        self.code_preview = QPlainTextEdit()
        self.code_preview.setObjectName("CodePreview")
        self.code_preview.setReadOnly(True)
        layout.addWidget(self.code_preview, 1)

    def _init_history_tab(self) -> None:
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(12, 12, 12, 12)

        hint = QLabel("💡 Double-click any past execution to inspect its structured evidence and output.")
        hint.setStyleSheet("color: #9ca3af; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(hint)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Executed At", "Status", "Duration", "Summary"])
        
        hist_header = self.history_table.horizontalHeader()
        hist_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hist_header.setStretchLastSection(True)
        hist_header.setCascadingSectionResizes(True)
        self.history_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.history_table.setColumnWidth(0, 150)
        self.history_table.setColumnWidth(1, 90)
        self.history_table.setColumnWidth(2, 90)

        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.cellDoubleClicked.connect(self._on_history_double_clicked)
        layout.addWidget(self.history_table, 1)

    def set_script_context(self, title: str, category: str = "") -> None:
        """Stores the active script context for audit report generation."""
        self._current_script_title = title
        if category:
            self._current_script_category = category

    def set_script_source(self, code: str) -> None:
        self.code_preview.setPlainText(code)

    def clear_raw_output(self) -> None:
        self.raw_console.clear()

    def append_raw_output(self, text: str) -> None:
        self.raw_console.moveCursor(self.raw_console.textCursor().MoveOperation.End)
        self.raw_console.insertPlainText(text)
        self.raw_console.moveCursor(self.raw_console.textCursor().MoveOperation.End)

    def display_run_result(
        self,
        result: RunResult,
        script_title: str = "",
        script_category: str = "",
    ) -> None:
        self._current_result = result
        if script_title:
            self._current_script_title = script_title
        elif result.script_title:
            self._current_script_title = result.script_title

        if script_category:
            self._current_script_category = script_category
        elif result.script_category:
            self._current_script_category = result.script_category

        # Enable reporting buttons
        self.copy_report_btn.setEnabled(True)
        self.save_report_btn.setEnabled(True)

        # Update Status Badge
        status_colors = {
            "pass": ("#065f46", "#34d399", "PASS"),
            "warning": ("#78350f", "#fbbf24", "WARNING"),
            "fail": ("#7f1d1d", "#f87171", "FAIL"),
            "error": ("#7f1d1d", "#f87171", "ERROR"),
            "timeout": ("#581c87", "#c084fc", "TIMEOUT"),
        }
        bg, fg, label = status_colors.get(result.status.lower(), ("#374151", "#9ca3af", result.status.upper()))
        self.status_badge.setText(label)
        self.status_badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; padding: 4px 12px; "
            "border-radius: 4px; font-weight: bold; font-size: 12px;"
        )

        self.duration_label.setText(f"Duration: {result.duration_ms} ms")
        self.exit_code_label.setText(f"Exit Code: {result.exit_code}")

        # Update Summary
        self.summary_box.setText(result.summary or "Execution completed.")
        self.summary_box.setStyleSheet(
            f"background-color: #1f2937; border-left: 4px solid {fg}; "
            "padding: 10px; border-radius: 4px; color: #f3f4f6;"
        )

        # Populate Structured Data Table with Resizable Columns
        self.data_table.clear()
        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            first_row = result.data[0]
            if isinstance(first_row, dict):
                columns = list(first_row.keys())
                self.data_table.setColumnCount(len(columns))
                self.data_table.setHorizontalHeaderLabels(columns)
                self.data_table.setRowCount(len(result.data))

                for r_idx, row_dict in enumerate(result.data):
                    for c_idx, col_name in enumerate(columns):
                        val_str = str(row_dict.get(col_name, ""))
                        item = QTableWidgetItem(val_str)
                        self.data_table.setItem(r_idx, c_idx, item)
            else:
                self.data_table.setColumnCount(1)
                self.data_table.setHorizontalHeaderLabels(["Value"])
                self.data_table.setRowCount(len(result.data))
                for r_idx, item_val in enumerate(result.data):
                    self.data_table.setItem(r_idx, 0, QTableWidgetItem(str(item_val)))
            
            # Auto-fit initial widths while keeping columns fully resizable
            self.data_table.resizeColumnsToContents()
            for c in range(self.data_table.columnCount()):
                col_w = self.data_table.columnWidth(c)
                if col_w < 110:
                    self.data_table.setColumnWidth(c, 110)
                elif col_w > 450:
                    self.data_table.setColumnWidth(c, 450)
        else:
            self.data_table.setColumnCount(1)
            self.data_table.setHorizontalHeaderLabels(["Output"])
            self.data_table.setRowCount(1)
            self.data_table.setItem(0, 0, QTableWidgetItem("No tabular data returned by script."))
            self.data_table.setColumnWidth(0, 300)

        # Errors / Warnings
        if result.errors:
            self.errors_label.setVisible(True)
            self.errors_box.setVisible(True)
            self.errors_box.setPlainText("\n".join(result.errors))
        else:
            self.errors_label.setVisible(False)
            self.errors_box.setVisible(False)

        # Switch to Results tab
        self.setCurrentIndex(0)

    def _on_copy_report_clicked(self) -> None:
        if not self._current_result:
            return
        title = self._current_script_title or self._current_result.script_title or "PowerShell Execution"
        category = self._current_script_category or self._current_result.script_category or "System"
        success = self.report_service.copy_ticket_report_to_clipboard(
            script_title=title,
            result=self._current_result,
            script_category=category,
        )
        if success:
            orig_text = self.copy_report_btn.text()
            self.copy_report_btn.setText("✓ Report Copied!")
            QTimer.singleShot(2000, lambda: self.copy_report_btn.setText(orig_text))
            self.status_message_requested.emit(
                "📋 Copied Rich-Text Ticket Report (HTML + Markdown) to Windows Clipboard!",
                4000,
            )

    def _on_save_report_clicked(self) -> None:
        if not self._current_result:
            return
        title = self._current_script_title or self._current_result.script_title or "execution_report"
        category = self._current_script_category or self._current_result.script_category or "System"
        slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in title).strip("_")
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Report_{slug}_{now_str}.html"
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Execution Report",
            str(default_dir / default_name),
            "HTML Files (*.html);;All Files (*)",
        )
        if file_path:
            try:
                saved_path = self.report_service.save_html_report(
                    file_path=file_path,
                    script_title=title,
                    result=self._current_result,
                    script_category=category,
                )
                self.status_message_requested.emit(
                    f"💾 Saved HTML Ticket Report to {saved_path.name}!",
                    5000,
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Failed to save report: {e}")

    def display_history(self, records: list[RunHistoryRecord]) -> None:
        self._history_records = records
        self.history_table.setRowCount(len(records))
        for row, rec in enumerate(records):
            time_item = QTableWidgetItem(rec.executed_at)
            status_item = QTableWidgetItem(rec.status.upper())
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rec.status.lower() == "pass":
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                status_item.setForeground(Qt.GlobalColor.red)

            dur_item = QTableWidgetItem(f"{rec.duration_ms} ms")
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sum_item = QTableWidgetItem(rec.summary)

            self.history_table.setItem(row, 0, time_item)
            self.history_table.setItem(row, 1, status_item)
            self.history_table.setItem(row, 2, dur_item)
            self.history_table.setItem(row, 3, sum_item)

    def _on_history_double_clicked(self, row: int, col: int) -> None:
        if hasattr(self, "_history_records") and 0 <= row < len(self._history_records):
            rec = self._history_records[row]
            data = []
            errors = []
            if rec.json_payload:
                try:
                    parsed = json.loads(rec.json_payload)
                    if isinstance(parsed, dict):
                        data = parsed.get("data", [])
                        errors = parsed.get("errors", [])
                except Exception:
                    pass

            hist_result = RunResult(
                script_id=rec.script_id,
                duration_ms=rec.duration_ms,
                exit_code=rec.exit_code,
                status=rec.status,
                summary=f"[History: {rec.executed_at}] {rec.summary}",
                data=data if isinstance(data, list) else [data],
                errors=errors if isinstance(errors, list) else [str(errors)],
                raw_output=rec.raw_output,
                raw_json=rec.json_payload,
                script_title=self._current_script_title,
                script_category=self._current_script_category,
            )
            self.display_run_result(hist_result)
            self.raw_console.setPlainText(rec.raw_output)
            self.setCurrentIndex(0)
