"""Page 4 — Algorithm selection and tuning parameters."""
from qgis.PyQt.QtWidgets import (
    QWizardPage, QVBoxLayout, QFormLayout, QLabel, QComboBox,
    QGroupBox, QCheckBox, QScrollArea, QWidget,
    QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QStackedWidget,
)
from qgis.PyQt.QtCore import Qt
from .ui_kit import (
    COLOR_MUTED, COLOR_WARNING, StatusLine, collapsible, dspin, ispin,
    opt_label, page_header,
)

# Algorithms grouped by required boat type.
_NORMAL_BOAT_ALGOS = [
    ("isofuel", "Isofuel (default)"),
    ("genetic", "Genetic algorithm"),
    ("gcr_slider", "GCR Slider"),
    ("dijkstra", "Dijkstra"),
]
_SPEEDY_BOAT_ALGOS = [
    ("speedy_isobased", "Speedy isobased (testing only)"),
    ("genetic_shortest_route", "Genetic (shortest route)"),
]

# Fixed stack position for each algorithm — independent of combo order.
_ALGO_STACK = {
    "isofuel": 0,
    "genetic": 1,
    "gcr_slider": 2,
    "dijkstra": 3,
    "genetic_shortest_route": 4,
    "speedy_isobased": 5,
}

from .defaults import (
    MINIMISATION_OPTIONS, PRUNE_GROUP_OPTIONS,
    SYMMETRY_AXIS_OPTIONS, GENETIC_POPULATION_OPTIONS, GENETIC_MUTATION_OPTIONS,
    GENETIC_CROSSOVER_OPTIONS, GENETIC_REPAIR_OPTIONS, GENETIC_CROSSOVER_PATCHER_OPTIONS
)


def _combo(options):
    c = QComboBox()
    for val, lbl in options:
        c.addItem(lbl, val)
    return c


class AlgorithmPage(QWizardPage):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.status = None
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        status_wrap = QWidget()
        sw = QVBoxLayout(status_wrap)
        sw.setContentsMargins(28, 0, 28, 12)
        self.status = StatusLine()
        sw.addWidget(self.status)
        outer.addWidget(status_wrap)

        root.addWidget(page_header(
            "Algorithm selection",
            "Choose the routing algorithm and tune its parameters.",
        ))

        # Algorithm picker
        pick_box = QGroupBox("Algorithm type")
        pick_form = QFormLayout(pick_box)
        pick_form.setLabelAlignment(Qt.AlignRight)
        # Combo is populated dynamically in initializePage based on boat type.
        self.algo_combo = QComboBox()
        self.algo_combo.currentIndexChanged.connect(self._on_algo_changed)
        pick_form.addRow(opt_label("Algorithm", "ALGORITHM_TYPE"), self.algo_combo)
        root.addWidget(pick_box)

        # Stacked param panels
        # Order is fixed and matches _ALGO_STACK indices.
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_isofuel_page())           # 0
        self.stack.addWidget(self._build_genetic_page())           # 1
        self.stack.addWidget(self._build_gcr_slider_page())        # 2
        self.stack.addWidget(self._build_dijkstra_page())          # 3
        self.stack.addWidget(self._build_genetic_shortest_page())  # 4
        self.stack.addWidget(self._build_speedy_page())            # 5
        root.addWidget(self.stack)

        root.addStretch()

    # Per-algorithm panels

    def _build_isofuel_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        req = QGroupBox("Required parameters")
        form = QFormLayout(req)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)
        self.iso_n_routes = ispin(val=1, mn=1)
        form.addRow(opt_label("Number of routes", "ISOCHRONE_NUMBER_OF_ROUTES"), self.iso_n_routes)
        v.addWidget(req)

        btn, box = collapsible("Advanced parameters")
        adv = QFormLayout(box)
        adv.setLabelAlignment(Qt.AlignRight)
        adv.setSpacing(8)
        self.iso_min_crit = _combo(MINIMISATION_OPTIONS)
        self.iso_max_steps = ispin(val=100)
        self.iso_prune_groups = _combo(PRUNE_GROUP_OPTIONS)
        self.iso_prune_half = ispin(val=91, mn=1, mx=180)
        self.iso_prune_segs = ispin(val=20, mn=1)
        self.iso_prune_sym = _combo(SYMMETRY_AXIS_OPTIONS)
        adv.addRow(opt_label("Minimisation criterion", "ISOCHRONE_MINIMISATION_CRITERION"), self.iso_min_crit)
        adv.addRow(opt_label("Max routing steps", "ISOCHRONE_MAX_ROUTING_STEPS"), self.iso_max_steps)
        adv.addRow(opt_label("Prune groups", "ISOCHRONE_PRUNE_GROUPS"), self.iso_prune_groups)
        adv.addRow(opt_label("Prune sector half (°)", "ISOCHRONE_PRUNE_SECTOR_DEG_HALF"), self.iso_prune_half)
        adv.addRow(opt_label("Prune segments", "ISOCHRONE_PRUNE_SEGMENTS"), self.iso_prune_segs)
        adv.addRow(opt_label("Prune symmetry axis", "ISOCHRONE_PRUNE_SYMMETRY_AXIS"), self.iso_prune_sym)
        v.addWidget(btn)
        v.addWidget(box)
        v.addStretch()
        return w

    def _build_genetic_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        req = QGroupBox("Required parameters")
        form = QFormLayout(req)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)
        self.gen_generations = ispin(val=20, mn=1)
        self.gen_obj_arrival = dspin(val=1.5, mn=0, mx=100, dec=2)
        self.gen_obj_fuel = dspin(val=1.5, mn=0, mx=100, dec=2)
        form.addRow(opt_label("Generations", "GENETIC_NUMBER_GENERATIONS"), self.gen_generations)
        form.addRow(QLabel("<b>Objective weights</b> (GENETIC_OBJECTIVES)"))
        form.addRow(opt_label("  Arrival time weight"), self.gen_obj_arrival)
        form.addRow(opt_label("  Fuel consumption weight"), self.gen_obj_fuel)
        v.addWidget(req)

        btn, box = collapsible("Advanced parameters")
        adv = QFormLayout(box)
        adv.setLabelAlignment(Qt.AlignRight)
        adv.setSpacing(8)
        self.gen_offsprings = ispin(val=2, mn=1)
        self.gen_pop_size = ispin(val=20, mn=2)
        self.gen_pop_type = _combo(GENETIC_POPULATION_OPTIONS)
        self.gen_pop_path = QLineEdit()
        self.gen_pop_path.setPlaceholderText("GeoJSON path (only for from_geojson)")
        gen_pop_browse = QPushButton("Browse…")
        gen_pop_browse.clicked.connect(lambda: self._browse(self.gen_pop_path, "GeoJSON (*.geojson *.json)"))
        pop_path_row = QHBoxLayout()
        pop_path_row.addWidget(self.gen_pop_path)
        pop_path_row.addWidget(gen_pop_browse)
        self.gen_repair = _combo(GENETIC_REPAIR_OPTIONS)
        self.gen_mutation = _combo(GENETIC_MUTATION_OPTIONS)
        self.gen_crossover = _combo(GENETIC_CROSSOVER_OPTIONS)
        self.gen_crossover_patcher = _combo(GENETIC_CROSSOVER_PATCHER_OPTIONS)
        self.gen_fix_seed = QCheckBox("Fix random seed (GENETIC_FIX_RANDOM_SEED)")
        adv.addRow(opt_label("Offsprings", "GENETIC_NUMBER_OFFSPRINGS"), self.gen_offsprings)
        adv.addRow(opt_label("Population size", "GENETIC_POPULATION_SIZE"), self.gen_pop_size)
        adv.addRow(opt_label("Population type", "GENETIC_POPULATION_TYPE"), self.gen_pop_type)
        adv.addRow(opt_label("Population path (GeoJSON)", "GENETIC_POPULATION_PATH"), pop_path_row)
        adv.addRow(opt_label("Repair strategy", "GENETIC_REPAIR_TYPE"), self.gen_repair)
        adv.addRow(opt_label("Mutation type", "GENETIC_MUTATION_TYPE"), self.gen_mutation)
        adv.addRow(opt_label("Crossover type", "GENETIC_CROSSOVER_TYPE"), self.gen_crossover)
        adv.addRow(opt_label("Crossover patcher", "GENETIC_CROSSOVER_PATCHER"), self.gen_crossover_patcher)
        adv.addRow(self.gen_fix_seed)
        v.addWidget(btn)
        v.addWidget(box)
        v.addStretch()
        return w

    def _build_gcr_slider_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        btn, box = collapsible("Advanced parameters")
        adv = QFormLayout(box)
        adv.setLabelAlignment(Qt.AlignRight)
        adv.setSpacing(8)
        self.gcr_angle_step = dspin(val=30, dec=1, suffix="°")
        self.gcr_distance_move = dspin(val=10000, dec=0, suffix="m")
        self.gcr_dynamic_params = QCheckBox("Dynamic parameters (GCR_SLIDER_DYNAMIC_PARAMETERS)")
        self.gcr_dynamic_params.setChecked(True)
        self.gcr_land_buffer = dspin(val=1000, dec=0, suffix="m")
        self.gcr_interpolate = QCheckBox("Interpolate (GCR_SLIDER_INTERPOLATE)")
        self.gcr_interpolate.setChecked(True)
        self.gcr_interp_dist = dspin(val=0.1, dec=3)
        self.gcr_interp_normalized = QCheckBox("Normalized interpolation (GCR_SLIDER_INTERP_NORMALIZED)")
        self.gcr_interp_normalized.setChecked(True)
        self.gcr_max_points = ispin(val=300, mn=1)
        self.gcr_threshold = dspin(val=10000, dec=0, suffix="m")
        adv.addRow(opt_label("Angle step", "GCR_SLIDER_ANGLE_STEP"), self.gcr_angle_step)
        adv.addRow(opt_label("Distance move", "GCR_SLIDER_DISTANCE_MOVE"), self.gcr_distance_move)
        adv.addRow(self.gcr_dynamic_params)
        adv.addRow(opt_label("Land buffer", "GCR_SLIDER_LAND_BUFFER"), self.gcr_land_buffer)
        adv.addRow(self.gcr_interpolate)
        adv.addRow(opt_label("Interpolation distance", "GCR_SLIDER_INTERP_DIST"), self.gcr_interp_dist)
        adv.addRow(self.gcr_interp_normalized)
        adv.addRow(opt_label("Max points", "GCR_SLIDER_MAX_POINTS"), self.gcr_max_points)
        adv.addRow(opt_label("Threshold", "GCR_SLIDER_THRESHOLD"), self.gcr_threshold)
        v.addWidget(btn)
        v.addWidget(box)
        v.addStretch()
        return w

    def _build_dijkstra_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        btn, box = collapsible("Advanced parameters")
        adv = QFormLayout(box)
        adv.setLabelAlignment(Qt.AlignRight)
        adv.setSpacing(8)
        self.dijk_neighbors = ispin(val=1, mn=1)
        self.dijk_step = ispin(val=1, mn=1)
        self.dijk_mask = QLineEdit()
        self.dijk_mask.setPlaceholderText("Auto (uses installed package path)")
        mask_browse = QPushButton("Browse…")
        mask_browse.clicked.connect(lambda: self._browse(self.dijk_mask, "NumPy (*.npz)"))
        mask_row = QHBoxLayout()
        mask_row.addWidget(self.dijk_mask)
        mask_row.addWidget(mask_browse)
        adv.addRow(opt_label("Num. neighbors", "DIJKSTRA_NOF_NEIGHBORS"), self.dijk_neighbors)
        adv.addRow(opt_label("Route save step", "DIJKSTRA_STEP"), self.dijk_step)
        adv.addRow(opt_label("Land mask file", "DIJKSTRA_MASK_FILE"), mask_row)
        v.addWidget(btn)
        v.addWidget(box)
        v.addStretch()
        return w

    def _build_genetic_shortest_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        note = QLabel(
            "Genetic shortest route optimises for the shortest path using the genetic "
            "algorithm with a <b>Speedy isobased</b> boat model. "
            "Configure genetic parameters on the <i>Genetic algorithm</i> panel."
        )
        note.setTextFormat(Qt.RichText)
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size: 12px; padding: 12px; color: {COLOR_MUTED};")
        v.addWidget(note)
        v.addStretch()
        return w

    def _build_speedy_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        note = QLabel("⚠  Speedy isobased is for testing only. No additional parameters.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 12px; padding: 12px;")
        v.addWidget(note)
        v.addStretch()
        return w

    # Helpers

    def _populate_algo_combo(self):
        """Fill the algorithm combo with only the algorithms valid for the current boat type."""
        boat = self.config.get("BOAT_TYPE", "direct_power_method")
        options = _SPEEDY_BOAT_ALGOS if boat == "speedy_isobased" else _NORMAL_BOAT_ALGOS
        self.algo_combo.blockSignals(True)
        self.algo_combo.clear()
        for val, lbl in options:
            self.algo_combo.addItem(lbl, val)
        self.algo_combo.blockSignals(False)

    def _update_status(self):
        if self.status is None:
            return  # still being constructed
        self.status.set_ok(f"Algorithm configured — {self.algo_combo.currentText()}")

    def _on_algo_changed(self, _idx):
        algo = self.algo_combo.currentData()
        self.stack.setCurrentIndex(_ALGO_STACK.get(algo, 0))
        self._update_status()

    def _browse(self, line_edit, file_filter):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", line_edit.text(), file_filter)
        if path:
            line_edit.setText(path)

    def _find_combo_idx(self, combo, data_val):
        idx = combo.findData(data_val)
        return idx if idx >= 0 else 0

    # Config persistence
    def save_to_config(self):
        c = self.config
        c["ALGORITHM_TYPE"] = self.algo_combo.currentData()
        # Isofuel
        c["ISOCHRONE_NUMBER_OF_ROUTES"] = self.iso_n_routes.value()
        c["ISOCHRONE_MINIMISATION_CRITERION"] = self.iso_min_crit.currentData()
        c["ISOCHRONE_MAX_ROUTING_STEPS"] = self.iso_max_steps.value()
        c["ISOCHRONE_PRUNE_GROUPS"] = self.iso_prune_groups.currentData()
        c["ISOCHRONE_PRUNE_SECTOR_DEG_HALF"] = self.iso_prune_half.value()
        c["ISOCHRONE_PRUNE_SEGMENTS"] = self.iso_prune_segs.value()
        c["ISOCHRONE_PRUNE_SYMMETRY_AXIS"] = self.iso_prune_sym.currentData()
        # Genetic
        c["GENETIC_NUMBER_GENERATIONS"] = self.gen_generations.value()
        c["GENETIC_OBJECTIVES"] = {
            "arrival_time": self.gen_obj_arrival.value(),
            "fuel_consumption": self.gen_obj_fuel.value(),
        }
        c["GENETIC_NUMBER_OFFSPRINGS"] = self.gen_offsprings.value()
        c["GENETIC_POPULATION_SIZE"] = self.gen_pop_size.value()
        c["GENETIC_POPULATION_TYPE"] = self.gen_pop_type.currentData()
        c["GENETIC_POPULATION_PATH"] = self.gen_pop_path.text()
        c["GENETIC_REPAIR_TYPE"] = self.gen_repair.currentData()
        c["GENETIC_MUTATION_TYPE"] = self.gen_mutation.currentData()
        c["GENETIC_CROSSOVER_TYPE"] = self.gen_crossover.currentData()
        c["GENETIC_CROSSOVER_PATCHER"] = self.gen_crossover_patcher.currentData()
        c["GENETIC_FIX_RANDOM_SEED"] = self.gen_fix_seed.isChecked()
        # GCR Slider
        c["GCR_SLIDER_ANGLE_STEP"] = self.gcr_angle_step.value()
        c["GCR_SLIDER_DISTANCE_MOVE"] = self.gcr_distance_move.value()
        c["GCR_SLIDER_DYNAMIC_PARAMETERS"] = self.gcr_dynamic_params.isChecked()
        c["GCR_SLIDER_LAND_BUFFER"] = self.gcr_land_buffer.value()
        c["GCR_SLIDER_INTERPOLATE"] = self.gcr_interpolate.isChecked()
        c["GCR_SLIDER_INTERP_DIST"] = self.gcr_interp_dist.value()
        c["GCR_SLIDER_INTERP_NORMALIZED"] = self.gcr_interp_normalized.isChecked()
        c["GCR_SLIDER_MAX_POINTS"] = self.gcr_max_points.value()
        c["GCR_SLIDER_THRESHOLD"] = self.gcr_threshold.value()
        # Dijkstra
        c["DIJKSTRA_NOF_NEIGHBORS"] = self.dijk_neighbors.value()
        c["DIJKSTRA_STEP"] = self.dijk_step.value()
        c["DIJKSTRA_MASK_FILE"] = self.dijk_mask.text()

    def initializePage(self):
        c = self.config
        # Repopulate combo for the current boat type, then restore saved algorithm.
        self._populate_algo_combo()
        algo = c.get("ALGORITHM_TYPE", "isofuel")
        idx = self.algo_combo.findData(algo)
        self.algo_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.stack.setCurrentIndex(_ALGO_STACK.get(self.algo_combo.currentData(), 0))
        # Isofuel
        self.iso_n_routes.setValue(int(c.get("ISOCHRONE_NUMBER_OF_ROUTES") or 1))
        self.iso_min_crit.setCurrentIndex(self._find_combo_idx(self.iso_min_crit, c.get("ISOCHRONE_MINIMISATION_CRITERION", "squareddist_over_disttodest")))
        self.iso_max_steps.setValue(int(c.get("ISOCHRONE_MAX_ROUTING_STEPS") or 100))
        self.iso_prune_groups.setCurrentIndex(self._find_combo_idx(self.iso_prune_groups, c.get("ISOCHRONE_PRUNE_GROUPS", "larger_direction")))
        self.iso_prune_half.setValue(int(c.get("ISOCHRONE_PRUNE_SECTOR_DEG_HALF") or 91))
        self.iso_prune_segs.setValue(int(c.get("ISOCHRONE_PRUNE_SEGMENTS") or 20))
        self.iso_prune_sym.setCurrentIndex(self._find_combo_idx(self.iso_prune_sym, c.get("ISOCHRONE_PRUNE_SYMMETRY_AXIS", "gcr")))
        # Genetic
        self.gen_generations.setValue(int(c.get("GENETIC_NUMBER_GENERATIONS") or 20))
        obj = c.get("GENETIC_OBJECTIVES") or {}
        self.gen_obj_arrival.setValue(float(obj.get("arrival_time", 1.5)))
        self.gen_obj_fuel.setValue(float(obj.get("fuel_consumption", 1.5)))
        self.gen_offsprings.setValue(int(c.get("GENETIC_NUMBER_OFFSPRINGS") or 2))
        self.gen_pop_size.setValue(int(c.get("GENETIC_POPULATION_SIZE") or 20))
        self.gen_pop_type.setCurrentIndex(self._find_combo_idx(self.gen_pop_type, c.get("GENETIC_POPULATION_TYPE", "isofuel")))
        self.gen_pop_path.setText(c.get("GENETIC_POPULATION_PATH", ""))
        self.gen_repair.setCurrentIndex(self._find_combo_idx(self.gen_repair, c.get("GENETIC_REPAIR_TYPE", "waypoints_infill")))
        self.gen_mutation.setCurrentIndex(self._find_combo_idx(self.gen_mutation, c.get("GENETIC_MUTATION_TYPE", "random")))
        self.gen_crossover.setCurrentIndex(self._find_combo_idx(self.gen_crossover, c.get("GENETIC_CROSSOVER_TYPE", "random")))
        self.gen_crossover_patcher.setCurrentIndex(self._find_combo_idx(self.gen_crossover_patcher, c.get("GENETIC_CROSSOVER_PATCHER", "isofuel")))
        self.gen_fix_seed.setChecked(bool(c.get("GENETIC_FIX_RANDOM_SEED", False)))
        # GCR Slider
        self.gcr_angle_step.setValue(float(c.get("GCR_SLIDER_ANGLE_STEP") or 30))
        self.gcr_distance_move.setValue(float(c.get("GCR_SLIDER_DISTANCE_MOVE") or 10000))
        self.gcr_dynamic_params.setChecked(bool(c.get("GCR_SLIDER_DYNAMIC_PARAMETERS", True)))
        self.gcr_land_buffer.setValue(float(c.get("GCR_SLIDER_LAND_BUFFER") or 1000))
        self.gcr_interpolate.setChecked(bool(c.get("GCR_SLIDER_INTERPOLATE", True)))
        self.gcr_interp_dist.setValue(float(c.get("GCR_SLIDER_INTERP_DIST") or 0.1))
        self.gcr_interp_normalized.setChecked(bool(c.get("GCR_SLIDER_INTERP_NORMALIZED", True)))
        self.gcr_max_points.setValue(int(c.get("GCR_SLIDER_MAX_POINTS") or 300))
        self.gcr_threshold.setValue(float(c.get("GCR_SLIDER_THRESHOLD") or 10000))
        # Dijkstra
        self.dijk_neighbors.setValue(int(c.get("DIJKSTRA_NOF_NEIGHBORS") or 1))
        self.dijk_step.setValue(int(c.get("DIJKSTRA_STEP") or 1))
        self.dijk_mask.setText(c.get("DIJKSTRA_MASK_FILE", ""))
        self._update_status()
