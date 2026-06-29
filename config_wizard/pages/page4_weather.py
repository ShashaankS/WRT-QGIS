"""Page 4 — Weather & depth datasets: file paths, time params, and NetCDF validation."""
import os
import re
from datetime import datetime, timedelta

from qgis.PyQt.QtWidgets import (
    QWizardPage, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QSpinBox, QHBoxLayout,
    QFileDialog
)
from qgis.PyQt.QtCore import Qt
from osgeo import gdal, osr

from ..ui.ui_kit import (
    COLOR_FILE_ERROR, COLOR_FILE_OK, COLOR_MUTED, COLOR_WARNING, StatusLine,
    opt_label, page_header,
)

UNIT_SECONDS = {
    "seconds": 1, "second": 1, "secs": 1, "sec": 1, "s": 1,
    "minutes": 60, "minute": 60, "mins": 60, "min": 60,
    "hours": 3600, "hour": 3600, "hrs": 3600, "hr": 3600, "h": 3600,
    "days": 86400, "day": 86400, "d": 86400,
}

def parse_time_units(units):
    """Parse a CF time-units string like 'hours since 1970-01-01 00:00:00'.

    :return: (seconds_per_unit, reference_datetime) or None if unparseable.
    """
    m = re.match(r"\s*(\w+)\s+since\s+(.+)", units, re.IGNORECASE)
    if not m:
        return None
    unit, ref = m.group(1).lower(), m.group(2).strip()
    if unit not in UNIT_SECONDS:
        return None
    # Normalise the reference date: drop trailing 'Z'/timezone, fractional secs.
    ref = ref.replace("T", " ").rstrip("Z").strip()
    ref = re.sub(r"\s+[+-]\d{1,2}:?\d{2}$", "", ref)      # strip +HH:MM offset
    ref = re.sub(r"\.\d+", "", ref)                       # strip fractional secs
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return UNIT_SECONDS[unit], datetime.strptime(ref, fmt)
        except ValueError:
            continue
    return None

def _datasets(path):
    """Open a file and yield a gdal dataset per geospatial variable.

    NetCDF variables are exposed as GDAL subdatasets (NETCDF:"file":var); a
    plain raster has none, so the root dataset itself is yielded.
    
    :raises ValueError: if the file cannot be opened by GDAL at all.
    """
    def _open(name):
        # GDAL <4 returns None on failure; GDAL 4 / UseExceptions() raises.
        try:
            return gdal.Open(name)
        except RuntimeError:
            return None

    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        root = _open(path)
        if root is None:
            raise ValueError("not a readable NetCDF/raster file")
        subs = root.GetSubDatasets()
        if not subs:
            yield root
            return
        for name, _desc in subs:
            ds = _open(name)
            if ds is not None:
                yield ds
    finally:
        gdal.PopErrorHandler()

def spatial_extent(ds, gt):
    """Return ((lat_min, lon_min, lat_max, lon_max), (dx, dy)) for a dataset.

    The extent is shrunk by half a cell so it describes the grid's cell-CENTRE
    coverage — the region where values can actually be interpolated — rather
    than GDAL's pixel-edge bounds. Coordinates are reprojected to WGS84 when the
    dataset declares a non-geographic CRS; NetCDF grids 
    usually carry none, in which case the raw lon/lat degrees are used as-is.
    """
    nx, ny = ds.RasterXSize, ds.RasterYSize
    dx, dy = abs(gt[1]), abs(gt[5])
    # Pixel-edge corners from the geotransform, then pull in half a cell.
    xs = sorted((gt[0], gt[0] + gt[1] * nx))
    ys = sorted((gt[3], gt[3] + gt[5] * ny))
    lon_min, lon_max = xs[0] + dx / 2, xs[1] - dx / 2
    lat_min, lat_max = ys[0] + dy / 2, ys[1] - dy / 2

    wkt = ds.GetProjection()
    if wkt:
        src = osr.SpatialReference()
        src.ImportFromWkt(wkt)
        if not src.IsGeographic():
            dst = osr.SpatialReference()
            dst.ImportFromEPSG(4326)
            dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            tr = osr.CoordinateTransformation(src, dst)
            corners = [tr.TransformPoint(x, y)[:2]
                       for x in (lon_min, lon_max) for y in (lat_min, lat_max)]
            lons = [c[0] for c in corners]
            lats = [c[1] for c in corners]
            lon_min, lon_max = min(lons), max(lons)
            lat_min, lat_max = min(lats), max(lats)
    return (lat_min, lon_min, lat_max, lon_max), (dx, dy)

def time_axis(ds):
    """Return (sorted_timestamps, calendar) for a dataset's CF time dimension.

    Reads the canonical GDAL metadata (`<dim>#units`, `<dim>#calendar`,
    `NETCDF_DIM_<dim>_VALUES`) rather than parsing per-band label strings, so it
    sees the full axis in order. Returns None if the dataset has no parseable
    time dimension (e.g. static bathymetry).
    """
    md = ds.GetMetadata()
    for key, units in md.items():
        if not key.endswith("#units") or "since" not in units.lower():
            continue
        dim = key[:-len("#units")]
        raw = md.get("NETCDF_DIM_%s_VALUES" % dim)
        parsed = parse_time_units(units)
        if not raw or not parsed:
            continue
        per_unit, ref = parsed
        try:
            values = [float(v) for v in raw.strip("{} ").split(",") if v.strip()]
        except ValueError:
            continue
        if not values:
            continue
        stamps = sorted(ref + timedelta(seconds=v * per_unit) for v in values)
        calendar = md.get("%s#calendar" % dim, "").lower()
        return stamps, calendar
    return None

def median_step_hours(stamps):
    """Median spacing between consecutive timestamps, in hours (None if <2)."""
    diffs = sorted((stamps[i + 1] - stamps[i]).total_seconds()
                   for i in range(len(stamps) - 1))
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    mid = len(diffs) // 2
    med = diffs[mid] if len(diffs) % 2 else (diffs[mid - 1] + diffs[mid]) / 2
    return med / 3600.0


def inspect_netcdf(path):
    """Inspect a NetCDF file's spatial extent and time dimension via GDAL.

    :return: dict with 'extent' (lat_min, lon_min, lat_max, lon_max), 'cell'
             (dx, dy in degrees) and, when a time axis is present, 'time'
             (min_dt, max_dt), 'time_step_hours' and 'calendar'.
    :raises ValueError: if the file cannot be opened or has no geospatial grid.
    """
    extent = cell = time_info = None
    for ds in _datasets(path):
        gt = ds.GetGeoTransform(can_return_null=True)
        if gt is None or ds.RasterXSize < 2 or ds.RasterYSize < 2:
            continue  # non-spatial variable (time_bnds, crs, …)
        if extent is None:
            extent, cell = spatial_extent(ds, gt)
        if time_info is None:
            time_info = time_axis(ds)
        if extent is not None and time_info is not None:
            break

    if extent is None:
        raise ValueError("no geospatial grid found (missing latitude/longitude)")

    info = {"extent": extent, "cell": cell}
    if time_info:
        stamps, calendar = time_info
        info["time"] = (stamps[0], stamps[-1])
        info["time_step_hours"] = median_step_hours(stamps)
        info["calendar"] = calendar
    return info


def lon_within(e_lon_min, e_lon_max, lon):
    """True if a WGS84 longitude falls in [e_lon_min, e_lon_max] under either the
    -180..180 or 0..360 convention."""
    return any(e_lon_min <= cand <= e_lon_max for cand in (lon, lon + 360, lon - 360))


def _covers(extent, lat_min, lon_min, lat_max, lon_max):
    e_lat_min, e_lon_min, e_lat_max, e_lon_max = extent
    return (e_lat_min <= lat_min <= e_lat_max and
            e_lat_min <= lat_max <= e_lat_max and
            lon_within(e_lon_min, e_lon_max, lon_min) and
            lon_within(e_lon_min, e_lon_max, lon_max))


# UI helpers
class _FileField(QGroupBox):
    """A group box with a file path input, browse button, and status label."""
    def __init__(self, title, placeholder, file_filter="NetCDF (*.nc)", parent=None):
        super().__init__(title, parent)
        self._filter = file_filter
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.status_lbl = QLabel("No file selected")
        self.status_lbl.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 11px;")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(placeholder)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", self.path_edit.text(), self._filter)
        if path:
            self.path_edit.setText(path)

    def set_status(self, text, color, bold=False):
        weight = "font-weight: bold; " if bold else ""
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color}; {weight}font-size: 11px;")

    def text(self):
        return self.path_edit.text()

    def setText(self, t):
        self.path_edit.setText(t)


class WeatherPage(QWizardPage):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._weather_valid = None   # None=no path, False=invalid, True=valid
        self._depth_valid = None
        self.status = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        root.addWidget(page_header(
            "Weather & depth datasets",
            "Upload weather and bathymetry NetCDF files. "
            "Files are validated against your route before you proceed.",
        ))

        self.weather_field = _FileField(
            "Weather data",
            "/path/to/weather.nc"
        )
        self.weather_field.path_edit.textChanged.connect(self._on_weather_changed)
        root.addWidget(self.weather_field)

        self.depth_field = _FileField(
            "Bathymetry data",
            "/path/to/depth.nc"
        )
        self.depth_field.path_edit.textChanged.connect(self._on_depth_changed)
        root.addWidget(self.depth_field)

        time_box = QGroupBox("Forecast time parameters")
        time_form = QFormLayout(time_box)
        time_form.setLabelAlignment(Qt.AlignRight)
        time_form.setSpacing(8)

        self.delta_time = QSpinBox()
        self.delta_time.setRange(1, 24)
        self.delta_time.setValue(3)
        self.delta_time.setSuffix("  h")
        self.delta_time.setToolTip("Time resolution of weather forecast (default: 3 h)")

        self.time_forecast = QSpinBox()
        self.time_forecast.setRange(1, 720)
        self.time_forecast.setValue(90)
        self.time_forecast.setSuffix("  h")
        self.time_forecast.setToolTip("Total forecast hours (default: 90 h)")
        # Re-check time coverage when the forecast horizon changes
        self.time_forecast.valueChanged.connect(
            lambda: self._validate_weather(self.weather_field.text().strip())
        )

        time_form.addRow(opt_label("Forecast time resolution", "DELTA_TIME_FORECAST"), self.delta_time)
        time_form.addRow(opt_label("Forecast horizon", "TIME_FORECAST"), self.time_forecast)
        root.addWidget(time_box)

        root.addStretch()

        self.status = StatusLine()
        root.addWidget(self.status)
        self._update_status()

    # Config helpers

    def _parse_map_coords(self):
        """Return (lat_min, lon_min, lat_max, lon_max) from config, or None."""
        val = self.config.get("DEFAULT_MAP", "")
        if not val:
            return None
        if isinstance(val, (list, tuple)) and len(val) == 4:
            try:
                return tuple(float(x) for x in val)
            except (ValueError, TypeError):
                return None
        if isinstance(val, str):
            parts = [p.strip() for p in val.split(",")]
            if len(parts) == 4:
                try:
                    return tuple(float(p) for p in parts)
                except ValueError:
                    return None
        return None

    def _parse_departure_time(self):
        """Return DEPARTURE_TIME as a naive datetime, or None."""
        val = self.config.get("DEPARTURE_TIME", "")
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.strptime(val, '%Y-%m-%dT%H:%MZ')
            except ValueError:
                return None
        return None

    # Validation

    def _validate(self, path, require_time):
        """Validate a NetCDF file; return (state, status_text, color, bold).

        state is True (valid), False (invalid) or None (no path given).
        """
        if not path:
            return None, "No file selected", COLOR_MUTED, False

        if not os.path.isfile(path):
            return False, "File not found", COLOR_FILE_ERROR, False

        size_mb = os.path.getsize(path) / (1024 * 1024)

        try:
            info = inspect_netcdf(path)
        except Exception as e:
            return False, f"✗  {e}", COLOR_FILE_ERROR, False

        extent = info["extent"]
        checks = []
        warns = []

        map_coords = self._parse_map_coords()
        if map_coords:
            lat_min, lon_min, lat_max, lon_max = map_coords
            if not _covers(extent, lat_min, lon_min, lat_max, lon_max):
                e_lat_min, e_lon_min, e_lat_max, e_lon_max = extent
                return (False,
                        f"✗  Spatial coverage [{e_lat_min:.2f}°, {e_lon_min:.2f}°, "
                        f"{e_lat_max:.2f}°, {e_lon_max:.2f}°] does not cover "
                        f"map [{lat_min}°, {lon_min}°, {lat_max}°, {lon_max}°]",
                        COLOR_FILE_ERROR, False)
            checks.append("spatial ✓")

        if require_time:
            if "time" not in info:
                return (False,
                        "✗  No time dimension found (required for weather data)",
                        COLOR_FILE_ERROR, False)
            departure = self._parse_departure_time()
            if departure:
                end = departure + timedelta(hours=self.time_forecast.value())
                t_min, t_max = info["time"]
                if not (t_min <= departure <= t_max and t_min <= end <= t_max):
                    return (False,
                            f"✗  Time coverage [{t_min:%Y-%m-%d %H:%M}, "
                            f"{t_max:%Y-%m-%d %H:%M}] does not cover routing period "
                            f"[{departure:%Y-%m-%d %H:%M}, {end:%Y-%m-%d %H:%M}]",
                            COLOR_FILE_ERROR, False)
                checks.append("time ✓")

        detail = "  ".join(checks) if checks else "structure OK"
        base = f"✓  {os.path.basename(path)}  —  {size_mb:.0f} MB  —  {detail}"
        if warns:
            return (True, base + "    ⚠ " + "; ".join(warns), COLOR_WARNING, True)
        return (True, base, COLOR_FILE_OK, True)

    def _validate_weather(self, path):
        state, text, color, bold = self._validate(path, require_time=True)
        self._weather_valid = state
        self.weather_field.set_status(text, color, bold)
        self._update_status()
        self.completeChanged.emit()

    def _validate_depth(self, path):
        if not path:
            self._depth_valid = None
            self.depth_field.set_status("Optional — leave blank to skip", COLOR_MUTED, False)
            self._update_status()
            self.completeChanged.emit()
            return
        state, text, color, bold = self._validate(path, require_time=False)
        self._depth_valid = state
        self.depth_field.set_status(text, color, bold)
        self._update_status()
        self.completeChanged.emit()

    def _update_status(self):
        if self.status is None:
            return  # still being constructed
        depth_ok = self._depth_valid is True or self._depth_valid is None
        if self._weather_valid is True and depth_ok:
            if self._depth_valid is True:
                self.status.set_ok("Weather & depth datasets validated")
            else:
                self.status.set_ok("Weather dataset validated (no bathymetry)")
            return
        if self._weather_valid is not True:
            self.status.set_pending("Provide valid weather data to continue")
        else:
            self.status.set_pending("Bathymetry file provided but invalid — fix or clear it to continue")

    def _on_weather_changed(self, text):
        self._validate_weather(text.strip())

    def _on_depth_changed(self, text):
        self._validate_depth(text.strip())

    def isComplete(self):
        depth_ok = self._depth_valid is True or self._depth_valid is None
        return self._weather_valid is True and depth_ok

    # Config persistence
    def save_to_config(self):
        self.config["WEATHER_DATA"] = self.weather_field.text().strip()
        self.config["DEPTH_DATA"] = self.depth_field.text().strip()
        self.config["DELTA_TIME_FORECAST"] = self.delta_time.value()
        self.config["TIME_FORECAST"] = self.time_forecast.value()

    def initializePage(self):
        self.weather_field.setText(self.config.get("WEATHER_DATA", ""))
        self.depth_field.setText(self.config.get("DEPTH_DATA", ""))
        self.delta_time.setValue(int(self.config.get("DELTA_TIME_FORECAST") or 3))
        self.time_forecast.setValue(int(self.config.get("TIME_FORECAST") or 90))
        # Validate any pre-filled paths (e.g. when user navigates back then forward)
        self._validate_weather(self.weather_field.text().strip())
        self._validate_depth(self.depth_field.text().strip())
