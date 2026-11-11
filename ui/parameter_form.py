from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from repositories.catalog_repo import ScriptRecord


class ParameterFormWidget(QFrame):
    values_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_script: ScriptRecord | None = None
        self._input_widgets: dict[str, QWidget] = {}
        self._param_definitions: list[dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        # Header with Reset button
        header_layout = QHBoxLayout()
        title = QLabel("SCRIPT PARAMETERS")
        title.setObjectName("SectionTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.reset_btn = QPushButton("↺ Reset Defaults")
        self.reset_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        header_layout.addWidget(self.reset_btn)
        self.main_layout.addLayout(header_layout)

        # Container for dynamic inputs
        self.form_container = QWidget()
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(8)
        self.main_layout.addWidget(self.form_container)

    def load_script(self, script: ScriptRecord) -> None:
        self._current_script = script
        self._param_definitions = script.params or []
        self._input_widgets.clear()

        # Clear existing layout items
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self._param_definitions:
            no_params_label = QLabel("No configurable parameters. Script runs with default configuration.")
            no_params_label.setStyleSheet("color: #6b7280; font-style: italic; padding: 4px 0;")
            self.form_layout.addWidget(no_params_label)
            self.reset_btn.setVisible(False)
            return

        self.reset_btn.setVisible(True)

        for param in self._param_definitions:
            name = param.get("name", "")
            param_type = str(param.get("type", "string")).lower()
            default_val = param.get("default")

            row_layout = QHBoxLayout()
            label = QLabel(f"${name}:")
            label.setMinimumWidth(110)
            label.setStyleSheet("font-weight: 500; color: #d1d5db;")
            row_layout.addWidget(label)

            if param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(default_val))
                widget.stateChanged.connect(self._emit_change)
                row_layout.addWidget(widget)
                row_layout.addStretch()
            elif param_type in ("int", "integer"):
                widget = QSpinBox()
                min_val = param.get("min", 0)
                max_val = param.get("max", 999999)
                widget.setRange(int(min_val), int(max_val))
                widget.setValue(int(default_val) if default_val is not None else 0)
                widget.valueChanged.connect(self._emit_change)
                row_layout.addWidget(widget, 1)
            else:  # string or default
                widget = QLineEdit()
                widget.setText(str(default_val) if default_val is not None else "")
                widget.textChanged.connect(self._emit_change)
                row_layout.addWidget(widget, 1)

            self._input_widgets[name] = widget
            self.form_layout.addLayout(row_layout)

    def get_parameter_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for param in self._param_definitions:
            name = param.get("name", "")
            param_type = str(param.get("type", "string")).lower()
            widget = self._input_widgets.get(name)
            if not widget:
                continue

            if param_type == "bool" and isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif param_type in ("int", "integer") and isinstance(widget, QSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()

        return values

    def reset_to_defaults(self) -> None:
        if not self._current_script:
            return
        self.load_script(self._current_script)
        self._emit_change()

    def _emit_change(self) -> None:
        self.values_changed.emit(self.get_parameter_values())

