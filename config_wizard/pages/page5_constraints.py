"""Page 5 — Constraints: checkboxes for each constraint type."""
from qgis.PyQt.QtWidgets import (
    QWizardPage, QVBoxLayout, QLabel, QCheckBox, QGroupBox
)
from qgis.PyQt.QtCore import Qt
from ..core.defaults import CONSTRAINT_OPTIONS
from ..ui.ui_kit import StatusLine, page_header

DEFAULT_CONSTRAINTS = ["land_crossing_global_land_mask", "water_depth", "on_map"]


class ConstraintsPage(QWizardPage):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.status = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        root.addWidget(page_header(
            "Constraints",
            "Select which constraints the routing algorithm must respect.",
        ))

        # Constraint checkboxes
        cons_box = QGroupBox("Active constraints    ")
        cons_layout = QVBoxLayout(cons_box)
        cons_layout.setSpacing(6)

        self.check_map = {}

        for val, label in CONSTRAINT_OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(val in DEFAULT_CONSTRAINTS)
            cb.toggled.connect(self._update_status)
            self.check_map[val] = cb
            cons_layout.addWidget(cb)

        root.addWidget(cons_box)

        # Info note
        note = QLabel(
            "<b>Note:</b> The 'via_waypoints' constraint is automatically enabled "
            "when intermediate waypoints are defined on the Route page."
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        note.setStyleSheet("color: gray; font-size: 11px; padding: 4px;")
        root.addWidget(note)

        root.addStretch()

        self.status = StatusLine()
        root.addWidget(self.status)
        self._update_status()

    def _update_status(self):
        if self.status is None:
            return  # still being constructed
        n = sum(1 for cb in self.check_map.values() if cb.isChecked())
        self.status.set_ok(f"{n} constraint{'' if n == 1 else 's'} selected")

    # Config persistence
    def save_to_config(self):
        active = [val for val, cb in self.check_map.items() if cb.isChecked()]
        # Auto-add via_waypoints if waypoints defined
        if self.config.get("INTERMEDIATE_WAYPOINTS") and "via_waypoints" not in active:
            active.append("via_waypoints")
        self.config["CONSTRAINTS_LIST"] = active

    def initializePage(self):

        if "CONSTRAINTS_LIST" in self.config:
            active = self.config["CONSTRAINTS_LIST"]
        else:
            active = DEFAULT_CONSTRAINTS
        for val, cb in self.check_map.items():
            cb.setChecked(val in active)
        self._update_status()
