"""Page 6 — Review & export: JSON preview and save-to-file."""
import json
import os
from qgis.PyQt.QtWidgets import (
    QWizardPage, QVBoxLayout, QLabel, QTextEdit, QPushButton,
    QHBoxLayout, QFileDialog, QMessageBox, QGroupBox
)
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtCore import Qt
from .ui_kit import StatusLine, join_terms, page_header


def _build_export(config):
    """Build the final JSON dict, stripping None/empty optional values."""
    out = {}
    skip_if_empty = {
        "ARRIVAL_TIME", "COURSES_FILE", "DIJKSTRA_MASK_FILE",
        "GENETIC_POPULATION_PATH", "BOAT_SPEED_MAX",
        "BOAT_AOD","BOAT_AXV","BOAT_AYV","BOAT_CMC","BOAT_HC",
        "BOAT_BS1","BOAT_HS1","BOAT_HS2","BOAT_LS1","BOAT_LS2",
    }
    for key, val in config.items():
        if val is None:
            continue
        if key in skip_if_empty and (val == "" or val == 0):
            continue
        if isinstance(val, float) and val == int(val):
            val = int(val)
        out[key] = val
    return out


class ReviewPage(QWizardPage):
    def __init__(self, config, pages, parent=None):
        super().__init__(parent)
        self.config = config
        self.pages = pages   # list of page objects with save_to_config()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(12)

        root.addWidget(page_header(
            "Review & export",
            "Review the generated configuration below. "
            "Copy it or save it to a JSON file to use with the WRT CLI.",
        ))

        # Summary labels
        self.summary_lbl = QLabel()
        self.summary_lbl.setTextFormat(Qt.RichText)
        self.summary_lbl.setWordWrap(True)
        root.addWidget(self.summary_lbl)

        # JSON preview
        json_box = QGroupBox("Generated config.json")
        json_layout = QVBoxLayout(json_box)
        self.json_edit = QTextEdit()
        self.json_edit.setReadOnly(False)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.Monospace)
        self.json_edit.setFont(mono)
        self.json_edit.setMinimumHeight(280)
        json_layout.addWidget(self.json_edit)
        root.addWidget(json_box)

        # Buttons
        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to clipboard")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("💾  Save as JSON…")
        save_btn.clicked.connect(self._save)
        save_btn.setDefault(True)
        cli_lbl = QLabel(
            '<span style="color:gray;font-size:11px;">CLI usage: '
            '<tt>python3 WeatherRoutingTool/cli.py -f /path/to/config.json</tt></span>'
        )
        cli_lbl.setTextFormat(Qt.RichText)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        root.addWidget(cli_lbl)

        self.status = StatusLine()
        root.addWidget(self.status)

    STEP_NAMES = [
        "Route", "Boat configuration", "Weather & depth",
        "Algorithm", "Constraints",
    ]

    def _update_status(self):
        assert len(self.pages) == len(self.STEP_NAMES), "page/name list mismatch"
        incomplete = [
            name for page, name in zip(self.pages, self.STEP_NAMES)
            if hasattr(page, "isComplete") and not page.isComplete()
        ]
        if incomplete:
            self.status.set_pending(
                "Some required fields are missing on: " + join_terms(incomplete)
            )
        else:
            self.status.set_ok("Configuration ready to export")

    def initializePage(self):
        # Flush all pages
        for page in self.pages:
            page.save_to_config()

        export = _build_export(self.config)
        json_str = json.dumps(export, indent=2)
        self.json_edit.setPlainText(json_str)

        self._update_status()

        # Summary
        route = self.config.get("DEFAULT_ROUTE", "—")
        algo = self.config.get("ALGORITHM_TYPE", "—")
        weather = os.path.basename(self.config.get("WEATHER_DATA", "")) or "—"
        depth = os.path.basename(self.config.get("DEPTH_DATA", "")) or "—"
        constraints = ", ".join(self.config.get("CONSTRAINTS_LIST", [])) or "none"
        self.summary_lbl.setText(
            f"<b>Route:</b> {route}<br>"
            f"<b>Algorithm:</b> {algo}<br>"
            f"<b>Weather:</b> {weather} &nbsp; <b>Depth:</b> {depth}<br>"
            f"<b>Constraints:</b> {constraints}"
        )

    def _get_json(self):
        return self.json_edit.toPlainText()

    def _copy(self):
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.clipboard().setText(self._get_json())
        QMessageBox.information(self, "Copied", "Configuration JSON copied to clipboard.")

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save WRT configuration", "config.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            # Validate JSON before writing
            json.loads(self._get_json())
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._get_json())
            QMessageBox.information(
                self, "Saved",
                f"Configuration saved to:\n{path}\n\n"
                f"Run with:\npython3 WeatherRoutingTool/cli.py -f {path}"
            )
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"The JSON is invalid:\n{e}")
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))
