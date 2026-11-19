from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from repositories.catalog_repo import ScriptRecord


def _alphanumeric_key(text: str) -> list[tuple[int, int | str]]:
    """Case-insensitive natural alphanumeric sort key (e.g. 'Task 2' < 'Task 10')."""
    parts = re.split(r"(\d+)", text.casefold())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts if p]


class CatalogTableView(QFrame):
    script_selected = Signal(object)  # ScriptRecord
    toggle_sidebar_requested = Signal()
    open_scripts_folder_requested = Signal()
    checked_scripts_changed = Signal(list)  # list[ScriptRecord]

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CatalogFrame")
        self._scripts: list[ScriptRecord] = []
        self._checked_scripts: dict[str, ScriptRecord] = {}
        self._sort_column: int | None = None
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
        self._init_ui()

    def _init_ui(self) -> None:
        # 0 margins on left/right so the table sticks flush to both sides of the pane
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        # Header Section with padding for title and controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 0, 10, 0)
        header_layout.setSpacing(8)

        self.toggle_sidebar_btn = QPushButton("◀ Sidebar")
        self.toggle_sidebar_btn.setToolTip("Toggle Categories & Filters sidebar (Ctrl+B)")
        self.toggle_sidebar_btn.setStyleSheet(
            "font-size: 11px; padding: 4px 8px; font-weight: 500;"
        )
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar_requested.emit)
        header_layout.addWidget(self.toggle_sidebar_btn)

        self.open_folder_btn = QPushButton("📂 Scripts Folder")
        self.open_folder_btn.setToolTip("Open the scripts/ catalog folder in File Explorer (Ctrl+O)")
        self.open_folder_btn.setStyleSheet(
            "font-size: 11px; padding: 4px 8px; font-weight: 500;"
        )
        self.open_folder_btn.clicked.connect(self.open_scripts_folder_requested.emit)
        header_layout.addWidget(self.open_folder_btn)

        self.header_label = QLabel("SCRIPT CATALOG")
        self.header_label.setObjectName("SectionTitle")
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        self.count_badge = QLabel("0 scripts")
        self.count_badge.setStyleSheet("color: #9ca3af; font-size: 11px;")
        header_layout.addWidget(self.count_badge)

        layout.addLayout(header_layout)

        # Compact batch selection toolbar
        batch_layout = QHBoxLayout()
        batch_layout.setContentsMargins(10, 0, 10, 0)
        batch_layout.setSpacing(6)

        self.check_all_btn = QPushButton("☑ Check All")
        self.check_all_btn.setToolTip(
            "Check all currently visible scripts in the catalog (Ctrl+Shift+A)"
        )
        self.check_all_btn.setStyleSheet(
            "font-size: 11px; padding: 3px 7px; font-weight: 500;"
        )
        self.check_all_btn.clicked.connect(self.check_all_visible)
        batch_layout.addWidget(self.check_all_btn)

        self.check_readonly_btn = QPushButton("☑ Read-Only")
        self.check_readonly_btn.setToolTip(
            "Check all visible READ-ONLY scripts (skips remediation scripts) (Ctrl+Shift+O)"
        )
        self.check_readonly_btn.setStyleSheet(
            "font-size: 11px; padding: 3px 7px; font-weight: 500;"
        )
        self.check_readonly_btn.clicked.connect(self.check_read_only_visible)
        batch_layout.addWidget(self.check_readonly_btn)

        self.clear_checked_btn = QPushButton("☐ Clear")
        self.clear_checked_btn.setToolTip(
            "Uncheck all selected scripts across all categories (Ctrl+Shift+D)"
        )
        self.clear_checked_btn.setStyleSheet(
            "font-size: 11px; padding: 3px 7px; font-weight: 500;"
        )
        self.clear_checked_btn.setEnabled(False)
        self.clear_checked_btn.clicked.connect(self.clear_checked_scripts)
        batch_layout.addWidget(self.clear_checked_btn)

        batch_layout.addStretch()

        self.checked_badge = QLabel("0 checked")
        self.checked_badge.setStyleSheet("color: #9ca3af; font-size: 11px;")
        batch_layout.addWidget(self.checked_badge)

        layout.addLayout(batch_layout)

        # Table — 3 columns stretching flush to both sides without empty dead space
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Title", "Risk Level", "Admin"])
        header_tooltips = (
            "Click to sort alphanumerically by Title",
            "Click to sort by Risk Level (READ-ONLY / REMEDIATION)",
            "Click to sort by Administrator requirement (No / Yes)",
        )
        for col_idx, tip in enumerate(header_tooltips):
            hdr_item = self.table.horizontalHeaderItem(col_idx)
            if hdr_item:
                hdr_item.setToolTip(tip)

        # Flush borders on left/right/bottom to integrate seamlessly with the pane
        self.table.setStyleSheet(
            "QTableWidget { border-left: none; border-right: none; border-bottom: none; border-radius: 0px 0px 7px 7px; }"
        )

        h_header = self.table.horizontalHeader()
        # Title column stretches to fill all available width to both sides
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Risk and Admin columns remain interactively resizable
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_header.setCascadingSectionResizes(True)
        h_header.setSectionsClickable(True)
        h_header.setSortIndicatorShown(True)
        h_header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        h_header.sectionClicked.connect(self._on_header_clicked)

        self.table.setColumnWidth(1, 115)  # Risk Level
        self.table.setColumnWidth(2, 85)   # Admin

        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_item_changed)

        layout.addWidget(self.table, 1)

    def set_sidebar_button_state(self, sidebar_visible: bool) -> None:
        """Updates the Sidebar button text and tooltip based on sidebar visibility."""
        if sidebar_visible:
            self.toggle_sidebar_btn.setText("◀ Sidebar")
            self.toggle_sidebar_btn.setToolTip("Collapse Categories & Filters sidebar (Ctrl+B)")
        else:
            self.toggle_sidebar_btn.setText("▶ Sidebar")
            self.toggle_sidebar_btn.setToolTip("Restore Categories & Filters sidebar (Ctrl+B)")

    def set_scripts(self, scripts: list[ScriptRecord]) -> None:
        self._scripts = list(scripts)
        self.count_badge.setText(
            f"{len(self._scripts)} script{'s' if len(self._scripts) != 1 else ''}"
        )
        self._populate_rows(self._sorted_scripts(self._scripts))

    def _sorted_scripts(self, scripts: list[ScriptRecord]) -> list[ScriptRecord]:
        if self._sort_column is None:
            return list(scripts)

        desc = self._sort_order == Qt.SortOrder.DescendingOrder
        if self._sort_column == 0:
            return sorted(scripts, key=lambda s: _alphanumeric_key(s.title), reverse=desc)
        if self._sort_column == 1:
            if desc:
                return sorted(
                    scripts,
                    key=lambda s: (
                        0 if s.risk_level == "remediation" else 1,
                        _alphanumeric_key(s.title),
                    ),
                )
            return sorted(
                scripts,
                key=lambda s: (
                    0 if s.risk_level != "remediation" else 1,
                    _alphanumeric_key(s.title),
                ),
            )
        if self._sort_column == 2:
            if desc:
                return sorted(
                    scripts,
                    key=lambda s: (0 if s.requires_admin else 1, _alphanumeric_key(s.title)),
                )
            return sorted(
                scripts,
                key=lambda s: (1 if s.requires_admin else 0, _alphanumeric_key(s.title)),
            )
        return list(scripts)

    def _on_header_clicked(self, column: int) -> None:
        self.sort_by_column(column)

    def sort_by_column(
        self, column: int, order: Qt.SortOrder | None = None
    ) -> None:
        """Sorts visible catalog scripts by column (0=Title, 1=Risk Level, 2=Admin)."""
        if column not in (0, 1, 2):
            return

        if order is not None:
            self._sort_column = column
            self._sort_order = order
        elif self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder

        self.table.horizontalHeader().setSortIndicator(
            self._sort_column, self._sort_order
        )

        # Preserve currently selected script across sort
        selected_path: str | None = None
        selected_items = self.table.selectedItems()
        if selected_items:
            row_item = self.table.item(selected_items[0].row(), 0)
            if row_item:
                selected_script = row_item.data(Qt.ItemDataRole.UserRole)
                if selected_script:
                    selected_path = selected_script.relative_path

        self._populate_rows(
            self._sorted_scripts(self._scripts),
            preserve_selected_path=selected_path,
        )

    def _populate_rows(
        self,
        scripts: list[ScriptRecord],
        preserve_selected_path: str | None = None,
    ) -> None:
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(scripts))
            target_select_row = 0 if scripts else -1
            for row, script in enumerate(scripts):
                # 0. Title Item (with checkable batch-selection box)
                title_item = QTableWidgetItem(script.title)
                title_item.setFlags(title_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if script.relative_path in self._checked_scripts:
                    self._checked_scripts[script.relative_path] = script
                    title_item.setCheckState(Qt.CheckState.Checked)
                else:
                    title_item.setCheckState(Qt.CheckState.Unchecked)
                title_item.setData(Qt.ItemDataRole.UserRole, script)
                self.table.setItem(row, 0, title_item)

                # 1. Risk Item with colored text/badge indicator
                risk_text = "REMEDIATION" if script.risk_level == "remediation" else "READ-ONLY"
                risk_item = QTableWidgetItem(risk_text)
                risk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if script.risk_level == "remediation":
                    risk_item.setForeground(Qt.GlobalColor.yellow)
                else:
                    risk_item.setForeground(Qt.GlobalColor.green)
                self.table.setItem(row, 1, risk_item)

                # 2. Requires Admin
                admin_text = "🛡️ Yes" if script.requires_admin else "No"
                admin_item = QTableWidgetItem(admin_text)
                admin_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if script.requires_admin:
                    admin_item.setForeground(Qt.GlobalColor.cyan)
                self.table.setItem(row, 2, admin_item)

                if preserve_selected_path and script.relative_path == preserve_selected_path:
                    target_select_row = row
        finally:
            self.table.blockSignals(False)

        self._update_checked_ui()

        if target_select_row >= 0:
            self.table.selectRow(target_select_row)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        script: ScriptRecord | None = item.data(Qt.ItemDataRole.UserRole)
        if not script:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_scripts[script.relative_path] = script
        else:
            self._checked_scripts.pop(script.relative_path, None)
        self._update_checked_ui()
        self.checked_scripts_changed.emit(self.get_checked_scripts())

    def get_checked_scripts(self) -> list[ScriptRecord]:
        return list(self._checked_scripts.values())

    def get_checked_count(self) -> int:
        return len(self._checked_scripts)

    def set_script_checked(self, relative_path: str, checked: bool) -> None:
        target_script: ScriptRecord | None = self._checked_scripts.get(relative_path)
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if not item:
                    continue
                script: ScriptRecord | None = item.data(Qt.ItemDataRole.UserRole)
                if script and script.relative_path == relative_path:
                    target_script = script
                    item.setCheckState(
                        Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                    )
                    break
        finally:
            self.table.blockSignals(False)

        if checked and target_script is not None:
            self._checked_scripts[relative_path] = target_script
        elif not checked:
            self._checked_scripts.pop(relative_path, None)

        self._update_checked_ui()
        self.checked_scripts_changed.emit(self.get_checked_scripts())

    def check_all_visible(self) -> None:
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if not item:
                    continue
                script: ScriptRecord | None = item.data(Qt.ItemDataRole.UserRole)
                if script:
                    self._checked_scripts[script.relative_path] = script
                item.setCheckState(Qt.CheckState.Checked)
        finally:
            self.table.blockSignals(False)

        self._update_checked_ui()
        self.checked_scripts_changed.emit(self.get_checked_scripts())

    def check_read_only_visible(self) -> int:
        """Checks all visible READ-ONLY scripts and unchecks visible remediation scripts."""
        checked_count = 0
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if not item:
                    continue
                script: ScriptRecord | None = item.data(Qt.ItemDataRole.UserRole)
                if not script:
                    continue
                if script.risk_level == "read_only":
                    self._checked_scripts[script.relative_path] = script
                    item.setCheckState(Qt.CheckState.Checked)
                    checked_count += 1
                else:
                    self._checked_scripts.pop(script.relative_path, None)
                    item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self.table.blockSignals(False)

        self._update_checked_ui()
        self.checked_scripts_changed.emit(self.get_checked_scripts())
        return checked_count

    def clear_checked_scripts(self) -> None:
        self._checked_scripts.clear()
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item:
                    item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self.table.blockSignals(False)

        self._update_checked_ui()
        self.checked_scripts_changed.emit([])

    def prune_checked_scripts(self, valid_relative_paths: set[str]) -> None:
        removed = [p for p in self._checked_scripts if p not in valid_relative_paths]
        if not removed:
            return
        for path in removed:
            self._checked_scripts.pop(path, None)
        self._update_checked_ui()
        self.checked_scripts_changed.emit(self.get_checked_scripts())

    def _update_checked_ui(self) -> None:
        count = len(self._checked_scripts)
        self.clear_checked_btn.setEnabled(count > 0)
        if count > 0:
            self.checked_badge.setText(f"{count} checked")
            self.checked_badge.setStyleSheet(
                "background-color: #1e3a8a; color: #93c5fd; padding: 2px 8px; "
                "border-radius: 4px; font-weight: 600; font-size: 11px;"
            )
        else:
            self.checked_badge.setText("0 checked")
            self.checked_badge.setStyleSheet("color: #9ca3af; font-size: 11px;")

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if item:
            script = item.data(Qt.ItemDataRole.UserRole)
            if script:
                self.script_selected.emit(script)

    def select_script_by_id(self, script_id: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                script: ScriptRecord = item.data(Qt.ItemDataRole.UserRole)
                if script and script.id == script_id:
                    self.table.selectRow(row)
                    break
