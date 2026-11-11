from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class SidebarView(QFrame):
    filter_changed = Signal(str, str, str, str)  # category, search, risk, edition
    sync_requested = Signal()

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarFrame")
        self._current_category = "All"
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header Title
        title = QLabel("PowerShellStore")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)

        subtitle = QLabel("IT & MSP Script Workstation")
        subtitle.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(subtitle)

        # Search Bar
        search_label = QLabel("SEARCH")
        search_label.setObjectName("SectionTitle")
        layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter title or synopsis...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_input)

        # Category Section
        cat_label = QLabel("CATEGORIES")
        cat_label.setObjectName("SectionTitle")
        layout.addWidget(cat_label)

        self.category_list = QListWidget()
        self.category_list.itemClicked.connect(self._on_category_clicked)
        layout.addWidget(self.category_list, 1)

        # Filters
        filter_label = QLabel("FILTERS")
        filter_label.setObjectName("SectionTitle")
        layout.addWidget(filter_label)

        risk_layout = QHBoxLayout()
        risk_text = QLabel("Risk:")
        risk_text.setStyleSheet("color: #9ca3af;")
        self.risk_combo = QComboBox()
        self.risk_combo.addItems(["All Risks", "read_only", "remediation"])
        self.risk_combo.currentTextChanged.connect(self._on_filter_changed)
        risk_layout.addWidget(risk_text)
        risk_layout.addWidget(self.risk_combo, 1)
        layout.addLayout(risk_layout)

        edition_layout = QHBoxLayout()
        edition_text = QLabel("Edition:")
        edition_text.setStyleSheet("color: #9ca3af;")
        self.edition_combo = QComboBox()
        self.edition_combo.addItems(["All Editions", "Desktop", "Core"])
        self.edition_combo.currentTextChanged.connect(self._on_filter_changed)
        edition_layout.addWidget(edition_text)
        edition_layout.addWidget(self.edition_combo, 1)
        layout.addLayout(edition_layout)

        # Sync Catalog Button
        self.sync_button = QPushButton("🔄 Sync Catalog")
        self.sync_button.clicked.connect(self.sync_requested.emit)
        layout.addWidget(self.sync_button)

    def update_categories(self, categories: list[dict[str, Any]], total_count: int) -> None:
        self.category_list.clear()

        all_item = QListWidgetItem(f"All Scripts ({total_count})")
        all_item.setData(100, "All")
        self.category_list.addItem(all_item)

        if self._current_category == "All":
            all_item.setSelected(True)

        for cat in categories:
            name = cat["category"]
            count = cat["count"]
            item = QListWidgetItem(f"{name} ({count})")
            item.setData(100, name)
            self.category_list.addItem(item)
            if self._current_category == name:
                item.setSelected(True)

    def _on_category_clicked(self, item: QListWidgetItem) -> None:
        category = item.data(100) or "All"
        self._current_category = category
        self._on_filter_changed()

    def _on_filter_changed(self) -> None:
        category = self._current_category
        search = self.search_input.text()
        risk = self.risk_combo.currentText()
        if risk == "All Risks":
            risk = "All"
        edition = self.edition_combo.currentText()
        if edition == "All Editions":
            edition = "All"
        self.filter_changed.emit(category, search, risk, edition)
