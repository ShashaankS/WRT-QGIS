"""Page 1 — Route: source, destination, waypoints, departure time, map bbox."""
from qgis.PyQt.QtWidgets import (
    QMessageBox,
    QWizardPage, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QDateTimeEdit, QWidget,
)
from qgis.PyQt.QtCore import Qt, QDateTime, pyqtSignal
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker

from ..ui.ui_kit import (
    COLOR_ARRIVAL, COLOR_GREEN, COLOR_MUTED, COLOR_ORANGE, COLOR_PRIMARY,
    COLOR_REQUIRED, LatLonField, StatusLine, clear_button, coord_input,
    field_label, format_coords, in_range, make_badge, make_dashed_badge,
    page_header, set_field_error,
)


class addWaypoint(QWidget):
    """The dashed '+ Click to add waypoint' placeholder row."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.badge = make_dashed_badge()
        self.hint = QLabel("Click to add waypoint")
        self.hint.setStyleSheet(
            f"color: {COLOR_MUTED}; border: 1px dashed #cfd4dc; border-radius: 8px;"
            "padding: 6px 10px; background: #fbfcfd;"
        )

        row.addWidget(self.badge)
        row.addWidget(self.hint, 1)
        # Phantom spacers matching the pick + clear buttons so rows stay aligned.
        for _ in range(2):
            spacer = QWidget()
            spacer.setFixedWidth(30)
            row.addWidget(spacer)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class RoutePage(QWizardPage):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.waypoint_rows = []
        self._iface = getattr(parent, "iface", None)
        self._previous_map_tool = None
        self._active_field = None
        self._active_label = None
        self._pick_map_tool = None
        self._pick_marker = None
        self.status = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(16)

        root.addWidget(page_header(
            "Route",
            "Set the source, destination, and departure time.",
        ))

        # Source / Destination
        self.src_field = LatLonField("S", COLOR_GREEN)
        self.dst_field = LatLonField("D", COLOR_ORANGE)
        self._wire_point(self.src_field, "source")
        self._wire_point(self.dst_field, "destination")

        sd_grid = QGridLayout()
        sd_grid.setHorizontalSpacing(28)
        sd_grid.setVerticalSpacing(6)
        sd_grid.addWidget(field_label("Source", required=True), 0, 0)
        sd_grid.addWidget(field_label("Destination", required=True), 0, 1)
        sd_grid.addWidget(self.src_field, 1, 0)
        sd_grid.addWidget(self.dst_field, 1, 1)
        sd_grid.setColumnStretch(0, 1)
        sd_grid.setColumnStretch(1, 1)
        root.addLayout(sd_grid)

        # Intermediate waypoints
        root.addWidget(field_label("Intermediate waypoints"))
        self.wp_container = QVBoxLayout()
        self.wp_container.setSpacing(8)
        root.addLayout(self.wp_container)

        self.add_row = addWaypoint()
        self.add_row.clicked.connect(self._on_add_waypoint_clicked)
        self.wp_container.addWidget(self.add_row)

        for wpt in self.config.get("INTERMEDIATE_WAYPOINTS", []):
            if len(wpt) == 2:
                field = self._add_waypoint()
                field.set_coords(float(wpt[0]), float(wpt[1]))

        # Departure / Arrival times
        self.dep_dt, dep_widget = self._make_dt_field("D", COLOR_ORANGE, clearable=False)
        self.dep_dt.setDateTime(QDateTime.currentDateTime())

        t_grid = QGridLayout()
        t_grid.setHorizontalSpacing(28)
        t_grid.setVerticalSpacing(6)
        t_grid.addWidget(field_label("Departure Time", required=True), 0, 0)
        t_grid.addWidget(dep_widget, 1, 0)
        t_grid.setColumnStretch(0, 1)
        t_grid.setColumnStretch(1, 1)
        root.addLayout(t_grid)

        # Advanced (bbox + output path)
        self.adv_toggle = QPushButton("▶  Advanced routing options")
        self.adv_toggle.setFlat(True)
        self.adv_toggle.setAutoDefault(False)
        self.adv_toggle.setDefault(False)
        self.adv_toggle.setCursor(Qt.PointingHandCursor)
        self.adv_toggle.setStyleSheet(
            "QPushButton { text-align: left; border: none; background: transparent;"
            f" padding: 4px 0; font-weight: 600; color: {COLOR_MUTED}; }}"
            "QPushButton:hover { background: transparent; color: " + COLOR_PRIMARY + "; }"
        )
        self.adv_toggle.clicked.connect(self._toggle_advanced)
        root.addWidget(self.adv_toggle)

        self.adv_widget = self._build_advanced()
        self.adv_widget.setVisible(False)
        root.addWidget(self.adv_widget)

        root.addStretch(1)

        # Status line
        self.status = StatusLine()
        root.addWidget(self.status)
        self._update_status()

    def _build_advanced(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(8)

        hint = QLabel(
            "Routing bounding box — leave blank to auto-derive from "
            "source/destination with a 2° buffer."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        lay.addWidget(hint)

        self.bbox_lat_min = coord_input("lat min", -90.0, 90.0)
        self.bbox_lon_min = coord_input("lon min", -180.0, 180.0)
        self.bbox_lat_max = coord_input("lat max", -90.0, 90.0)
        self.bbox_lon_max = coord_input("lon max", -180.0, 180.0)
        bbox_row = QHBoxLayout()
        for w in (self.bbox_lat_min, self.bbox_lon_min, self.bbox_lat_max, self.bbox_lon_max):
            w.textChanged.connect(self._on_bbox_changed)
            bbox_row.addWidget(w)
        lay.addLayout(bbox_row)

        self.bbox_msg = QLabel()
        self.bbox_msg.setWordWrap(True)
        self.bbox_msg.setStyleSheet(f"color: {COLOR_REQUIRED}; font-size: 11px;")
        self.bbox_msg.setVisible(False)
        lay.addWidget(self.bbox_msg)

        lay.addWidget(field_label("Route output file", required=True))
        self.route_path = QLineEdit(self.config.get("ROUTE_PATH", "/tmp/wrt_route.json"))
        self.route_path.textChanged.connect(lambda: self.completeChanged.emit())
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_route_path)
        rp_row = QHBoxLayout()
        rp_row.addWidget(self.route_path, 1)
        rp_row.addWidget(browse_btn)
        lay.addLayout(rp_row)
        return box

    def _make_dt_field(self, badge_text, color, clearable):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        badge = make_badge(badge_text, color)
        dt = QDateTimeEdit()
        dt.setDisplayFormat("dd/MM/yyyy - hh:mm AP")
        dt.setCalendarPopup(True)
        dt.setTimeSpec(Qt.LocalTime)
        dt.dateTimeChanged.connect(self._update_status)

        row.addWidget(badge)
        row.addWidget(dt, 1)

        if clearable:
            btn = clear_button("Clear arrival time")
            btn.clicked.connect(lambda: dt.setDateTime(dt.minimumDateTime()))
            row.addWidget(btn)
        else:
            spacer = QWidget()
            spacer.setFixedWidth(30)
            row.addWidget(spacer)
        return dt, container

    def _toggle_advanced(self):
        visible = not self.adv_widget.isVisible()
        self.adv_widget.setVisible(visible)
        self.adv_toggle.setText(
            ("▼" if visible else "▶") + "  Advanced routing options"
        )

    # Point / waypoint wiring
    def _wire_point(self, field, label):
        field.pick_requested.connect(lambda: self._start_map_pick(field, label))
        field.action_clicked.connect(field.clear)
        field.changed.connect(self._on_field_changed)

    def _on_field_changed(self):
        self._update_status()
        self.completeChanged.emit()

    def _on_add_waypoint_clicked(self):
        self._add_waypoint()

    def _add_waypoint(self, lat=None, lon=None):
        idx = len(self.waypoint_rows) + 1
        field = LatLonField(str(idx), COLOR_PRIMARY)
        field.pick_requested.connect(lambda f=field: self._start_map_pick(f, "waypoint"))
        field.changed.connect(self._on_field_changed)

        entry = {"field": field}
        self.waypoint_rows.append(entry)

        # Insert above the add-row placeholder.
        self.wp_container.insertWidget(self.wp_container.count() - 1, field)

        def remove():
            self.waypoint_rows.remove(entry)
            field.setParent(None)
            self._renumber_waypoints()
            self._update_status()
        field.action_clicked.connect(remove)

        if lat is not None and lon is not None:
            field.set_coords(float(lat), float(lon))
        return field

    def _renumber_waypoints(self):
        for i, entry in enumerate(self.waypoint_rows):
            entry["field"].set_badge_text(i + 1)

    # Bounding-box validation
    def _bbox_state(self):
        """Classify the advanced bbox inputs: ('empty'|'partial'|'invalid'|'order'|'ok', msg)."""
        fields = (self.bbox_lat_min, self.bbox_lon_min, self.bbox_lat_max, self.bbox_lon_max)
        texts = [f.text().strip() for f in fields]
        if not any(texts):
            return ("empty", "")
        if not all(texts):
            return ("partial", "Enter all four bounding-box values, or leave them all blank.")
        if not (in_range(self.bbox_lat_min) and in_range(self.bbox_lat_max)):
            return ("invalid", "Latitudes must be numbers between −90 and 90.")
        if not (in_range(self.bbox_lon_min) and in_range(self.bbox_lon_max)):
            return ("invalid", "Longitudes must be numbers between −180 and 180.")
        lat_min, lon_min = float(texts[0]), float(texts[1])
        lat_max, lon_max = float(texts[2]), float(texts[3])
        if lat_min >= lat_max or lon_min >= lon_max:
            return ("order", "Min values must be smaller than max values (lat min < lat max, lon min < lon max).")
        return ("ok", "")

    def _on_bbox_changed(self):
        state, msg = self._bbox_state()
        # Red-border any individual field that is non-empty and out of range.
        for f in (self.bbox_lat_min, self.bbox_lon_min, self.bbox_lat_max, self.bbox_lon_max):
            set_field_error(f, bool(f.text().strip()) and not in_range(f))
        self.bbox_msg.setText(msg)
        self.bbox_msg.setVisible(bool(msg))
        self._update_status()
        self.completeChanged.emit()

    def _browse_route_path(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Route output file", self.route_path.text(), "JSON (*.json)")
        if path:
            self.route_path.setText(path)

    # Status / completion
    def _update_status(self):
        if self.status is None:
            return  # still being constructed
        have_src = self.src_field.get_coords() is not None
        have_dst = self.dst_field.get_coords() is not None
        missing = []
        if not have_src:
            missing.append("source")
        if not have_dst:
            missing.append("destination")
        if missing:
            self.status.set_pending("Set " + " and ".join(missing) + " to continue")
            return
        bbox_state, bbox_msg = self._bbox_state()
        if bbox_state not in ("empty", "ok"):
            self.status.set_pending("Bounding box — " + bbox_msg)
            return
        self.status.set_ok("Source, destination & departure time set")

    def isComplete(self):
        return bool(
            self.src_field.get_coords() is not None and
            self.dst_field.get_coords() is not None and
            self.route_path.text().strip() and
            self._bbox_state()[0] in ("empty", "ok")
        )

    # Config persistence
    def save_to_config(self):
        src = self.src_field.get_coords()
        dst = self.dst_field.get_coords()
        if src and dst:
            self.config["DEFAULT_ROUTE"] = f"{src[0]},{src[1]},{dst[0]},{dst[1]}"

        self.config["DEPARTURE_TIME"] = self.dep_dt.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm") + "Z"
        self.config["ROUTE_PATH"] = self.route_path.text()

        waypoints = []
        for entry in self.waypoint_rows:
            coords = entry["field"].get_coords()
            if coords is not None:
                waypoints.append([coords[0], coords[1]])
        self.config["INTERMEDIATE_WAYPOINTS"] = waypoints

        # Build bbox — only use the manual values when they form a valid box, otherwise auto-derive (avoids persisting a partial/invalid bbox).
        if self._bbox_state()[0] == "ok":
            self.config["DEFAULT_MAP"] = (
                f"{self.bbox_lat_min.text()},{self.bbox_lon_min.text()},"
                f"{self.bbox_lat_max.text()},{self.bbox_lon_max.text()}"
            )
        elif src and dst:
            lat_s, lon_s = src
            lat_d, lon_d = dst
            buf = 2.0
            self.config["DEFAULT_MAP"] = (
                f"{min(lat_s, lat_d) - buf},{min(lon_s, lon_d) - buf},"
                f"{max(lat_s, lat_d) + buf},{max(lon_s, lon_d) + buf}"
            )
        else:
            self.config["DEFAULT_MAP"] = ""

    def initializePage(self):
        route = self.config.get("DEFAULT_ROUTE", "")
        if route:
            parts = [p.strip() for p in route.split(",")]
            if len(parts) == 4:
                try:
                    self.src_field.set_coords(float(parts[0]), float(parts[1]))
                    self.dst_field.set_coords(float(parts[2]), float(parts[3]))
                except ValueError:
                    pass
        dep_str = self.config.get("DEPARTURE_TIME", "")
        if dep_str:
            utc_dt = QDateTime.fromString(dep_str, "yyyy-MM-ddTHH:mmZ")
            if utc_dt.isValid():
                utc_dt.setTimeSpec(Qt.UTC)
                self.dep_dt.setDateTime(utc_dt.toLocalTime())
        self.route_path.setText(self.config.get("ROUTE_PATH", "/tmp/wrt_route.json"))
        self._update_status()

    # Map picking
    def _start_map_pick(self, field, label):
        if self._iface is None:
            return

        self._active_field = field
        self._active_label = label

        window = self.window()
        if window is not None:
            window.hide()

        main_window = self._iface.mainWindow()
        main_window.raise_()
        main_window.activateWindow()

        canvas = self._iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()

        map_tool = QgsMapToolEmitPoint(canvas)
        map_tool.canvasClicked.connect(self._handle_map_click)
        canvas.setMapTool(map_tool)
        self._pick_map_tool = map_tool

        self._iface.messageBar().pushInfo(
            "Weather Routing Tool",
            f"Click on the map to set the {label} location. Right-click to cancel.",
        )

    def _clear_pick_marker(self):
        if self._pick_marker is not None:
            canvas = self._iface.mapCanvas() if self._iface is not None else None
            if canvas is not None:
                canvas.scene().removeItem(self._pick_marker)
            self._pick_marker = None

    def _restore_window(self):
        window = self.window()
        if window is None:
            return
        window.show()
        window.raise_()
        window.activateWindow()

    def _finish_pick(self):
        """End the whole pick session: restore the previous tool and the wizard."""
        if self._iface is not None and self._previous_map_tool is not None:
            self._iface.mapCanvas().setMapTool(self._previous_map_tool)
        if self._iface is not None:
            self._iface.messageBar().clearWidgets()

        self._clear_pick_marker()
        self._restore_window()

        self._active_field = None
        self._active_label = None
        self._previous_map_tool = None
        self._pick_map_tool = None

    def _show_marker(self, canvas, point):
        self._clear_pick_marker()
        self._pick_marker = QgsVertexMarker(canvas)
        self._pick_marker.setCenter(point)
        self._pick_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self._pick_marker.setColor(Qt.red)
        self._pick_marker.setPenWidth(3)
        self._pick_marker.setIconSize(16)

    def _handle_map_click(self, point, button):
        if self._iface is None:
            return

        # Right-click aborts the entire pick and returns to the wizard.
        if button == Qt.RightButton:
            self._finish_pick()
            return

        canvas = self._iface.mapCanvas()
        point_wgs84 = point

        canvas_crs = canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if canvas_crs != wgs84:
            transform = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
            point_wgs84 = transform.transform(point)

        self._show_marker(canvas, point)

        lat = point_wgs84.y()
        lon = point_wgs84.x()

        prompt = QMessageBox(self._iface.mainWindow())
        prompt.setIcon(QMessageBox.Question)
        prompt.setWindowTitle("Confirm location")
        prompt.setWindowModality(Qt.ApplicationModal)
        prompt.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        label = self._active_label or "selected"
        prompt.setText(
            f"Use this location for the {label} point?\n{format_coords(lat, lon)}"
        )
        use_btn = prompt.addButton("Use this location", QMessageBox.AcceptRole)
        prompt.addButton("Pick again", QMessageBox.RejectRole)
        prompt.setDefaultButton(use_btn)
        prompt.raise_()
        prompt.activateWindow()

        prompt.exec_()
        if prompt.clickedButton() is not use_btn:
            self._clear_pick_marker()
            return

        if self._active_field is not None:
            self._active_field.set_coords(lat, lon)

        self._finish_pick()
