from __future__ import annotations

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


class CatalogTableView(QFrame):
    script_selected = Signal(object)  # ScriptRecord
    toggle_sidebar_requested = Signal()

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CatalogFrame")
        self._scripts: list[ScriptRecord] = []
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

        self.header_label = QLabel("SCRIPT CATALOG")
        self.header_label.setObjectName("SectionTitle")
        header_layout.addWidget(self.header_label)

        header_layout.addStretch()

        self.count_badge = QLabel("0 scripts")
        self.count_badge.setStyleSheet("color: #9ca3af; font-size: 11px;")
        header_layout.addWidget(self.count_badge)

        layout.addLayout(header_layout)

        # Table — 3 columns stretching flush to both sides without empty dead space
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Title", "Risk Level", "Admin"])

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

        self.table.setColumnWidth(1, 115)  # Risk Level
        self.table.setColumnWidth(2, 85)   # Admin

        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

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
        self._scripts = scripts
        self.table.setRowCount(len(scripts))
        self.count_badge.setText(f"{len(scripts)} script{'s' if len(scripts) != 1 else ''}")

        for row, script in enumerate(scripts):
            # 0. Title Item
            title_item = QTableWidgetItem(script.title)
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

        if scripts:
            self.table.selectRow(0)

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
