import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import xml.etree.ElementTree as ET
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from utils.gcode_handling import resetOutputFile
from utils.app_paths import save_last_project_folder
import config

PATH_MODES = [
    "simple contour",
    "skeletonized lines",
    "inward offset fill",
    "lawnmover fill",
    "AM fill full canvas",
    "AM fill inside contours",
    "trace SVG",
    "foam voronoi cells",
    "billiard bounce fill",
    "spiral fill",
    "AM spiral fill full canvas",
    "AM spiral fill inside contours",
    "dot fill full canvas",
    "dot fill inside contours",
    "TSP art full canvas",
    "TSP art inside contours"
]

# Which mode-specific control frame(s) (see _mode_frame()) apply to each
# path generation mode. Modes not listed here (or mapped to an empty list)
# have no extra parameters beyond General / Visualisation / Polygon controls.
MODE_SECTION_KEYS = {
    config.mode_simple_contour: [],
    config.mode_skeletonized_lines: [],
    config.mode_inward_offset_fill: ["inward_offset"],
    config.mode_lawnmover_fill: ["lawnmower"],
    config.mode_AM_fill_full_canvas: ["am_fill"],
    config.mode_AM_fill_inside_contours: ["am_fill"],
    config.mode_trace_svg: ["svg_trace"],
    config.mode_foam_voronoi: ["foam_voronoi"],
    config.mode_billiard_fill: ["billiard_fill"],
    config.mode_spiral_fill: ["spiral_fill"],
    config.mode_AM_spiral_fill_full_canvas: ["am_spiral_fill"],
    config.mode_AM_spiral_fill_inside_contours: ["am_spiral_fill"],
    config.mode_dot_fill_full_canvas: ["dot_fill"],
    config.mode_dot_fill_inside_contours: ["dot_fill"],
    config.mode_tsp_art_full_canvas: ["tsp_art"],
    config.mode_tsp_art_inside_contours: ["tsp_art"],
}


class LayerEditor:
    def __init__(self, root, xml_path, update_callback, figSource, figPreview):
        self.root = root
        self.xml_path = xml_path
        self.update_callback = update_callback

        if not os.path.exists(self.xml_path):
            # No XML in the startup folder (e.g. first run, or the folder
            # picker at launch was removed) -- create a minimal default one
            # instead of crashing.
            self._create_default_xml(self.xml_path)

        self.tree = ET.parse(self.xml_path)
        self.root_elem = self.tree.getroot()
        self.layers = self.root_elem.findall("layer")

        if not self.layers:
            # Empty <layers/> file -- give the editor at least one layer
            # to work with.
            self.root_elem.append(self._new_default_layer_element())
            self.layers = self.root_elem.findall("layer")
            self.tree.write(self.xml_path)

        self.current_layer = 0


        self.project_folder = tk.StringVar(value=os.getcwd())
        self._build_ui(figSource, figPreview)
        self.load_layer(0)

    # ---------------------------------------------------------
    # UI construction (GRID BASED)
    # ---------------------------------------------------------
    
    
    def update_source_preview(self):
        path = self.source_path.get()
        
        self.ax_source.clear()  # remove old content

        if not path:
            self.canvas_source.draw_idle()
            return

        try:
            if path.lower().endswith(".svg"):
                # Vector source: draw the traced lines directly, no rasterization
                from utils.svg_tracer import trace_svg_lines
                svg_lines, svg_w, svg_h = trace_svg_lines(path)
                for line in svg_lines:
                    xs = [p[0] for p in line]
                    ys = [svg_h - p[1] for p in line]
                    self.ax_source.plot(xs, ys, color="black", linewidth=0.8)
                self.ax_source.set_xlim(0, svg_w)
                self.ax_source.set_ylim(0, svg_h)
            else:
                import cv2
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise ValueError("Image could not be loaded")
                if img.ndim == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                # Display image with correct aspect ratio
                self.ax_source.imshow(img)

            # Remove everything from axes
            self.ax_source.set_xticks([])
            self.ax_source.set_yticks([])
            self.ax_source.set_frame_on(False)
            for spine in self.ax_source.spines.values():
                spine.set_visible(False)
            self.ax_source.axis('off')
            self.ax_source.grid(False)

            # Force the axes to have the same aspect ratio as the image
            self.ax_source.set_aspect('equal')

            print("AX ID:", id(self.ax_preview))
            print("FIG AXES:", [id(a) for a in self.fig_preview.axes])

        except Exception as e:
            self.ax_source.text(
                0.5, 0.5,
                f"Failed to load image\n{e}",
                ha="center", va="center",
                transform=self.ax_source.transAxes
            )
            self.ax_source.axis("off")

        self.canvas_source.draw_idle()



    def _build_ui(self, figSource, figPreview):
        main = ttk.Frame(self.root, padding=8)
        main.grid(sticky="nsew")

        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # column layout
        main.columnconfigure(0, weight=0)   # source
        main.columnconfigure(1, weight=1)   # path preview
        main.columnconfigure(2, weight=0)   # controls

        # row layout
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)

        # frames
        source = ttk.Frame(main, padding=6)
        sourcePreview = ttk.Frame(main, padding=6)
        pathPreview = ttk.Frame(main, padding=6)
        controls = ttk.Frame(main, padding=6)

        source.grid(row=0, column=0, sticky="nw")
        sourcePreview.grid(row=1, column=0, sticky="nw")

        pathPreview.grid(row=0, column=1, rowspan=2, sticky="nsew")
        controls.grid(row=0, column=2, rowspan=2, sticky="nsew")

        sourcePreview.rowconfigure(0, weight=1)
        sourcePreview.rowconfigure(1, weight=0)
        sourcePreview.columnconfigure(0, weight=0)
        sourcePreview.columnconfigure(1, weight=1)
        pathPreview.rowconfigure(0, weight=0)
        pathPreview.rowconfigure(1, weight=1)
        pathPreview.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        # ---------------- Source ----------------
        r = 0

        ttk.Label(source, text="Project Folder", font=("Segoe UI", 9, "bold"))\
            .grid(row=r, column=0, sticky="w", pady=(10, 4)); r += 1

        self.project_folder_entry = ttk.Entry(
            source,
            textvariable=self.project_folder,
            width=50
        )

        
        self.project_folder_entry.grid(row=r, column=0, sticky="ew"); r += 1

        ttk.Button(source, text="Select Project Folder", command=self.select_project_folder)\
            .grid(row=r, column=0, sticky="ew", pady=(4, 2)); r += 1
        ttk.Button(source, text="Create New Project Folder", command=self.create_project_folder)\
            .grid(row=r, column=0, sticky="ew", pady=(0, 2)); r += 1

        ttk.Label(source, text="Layer", font=("Segoe UI", 9, "bold"))\
            .grid(row=r, column=0, sticky="w", pady=(10, 4)); r += 1

        self.layer_select = ttk.Combobox(
            source, values=list(range(1, len(self.layers) + 1)), width=10
        )
        self.layer_select.current(0)
        self.layer_select.grid(row=r, column=0, sticky="w"); r += 1
        self.layer_select.bind("<<ComboboxSelected>>", self.change_layer)

        ttk.Button(source, text="Add New Layer", command=self.add_layer)\
            .grid(row=r, column=0, sticky="ew", pady=2); r += 1
        ttk.Button(source, text="Delete Current Layer", command=self.remove_layer)\
            .grid(row=r, column=0, sticky="ew", pady=2); r += 1

        self.layer_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(source, text="Enable layer", variable=self.layer_enabled)\
            .grid(row=r, column=0, sticky="w", pady=(4, 8)); r += 1

        ttk.Label(source, text="Source", font=("Segoe UI", 9, "bold"))\
            .grid(row=r, column=0, sticky="w", pady=(10, 4)); r += 1

        self.source_path = ttk.Entry(source, width=30)
        self.source_path.grid(row=r, column=0, sticky="ew"); r += 1

        ttk.Button(source, text="Browse", command=self.browse_image)\
            .grid(row=r, column=0, sticky="ew")

        # ---------------- Source preview ----------------
        self.fig_source = figSource
        self.ax_source = self.fig_source.add_subplot(111)
        self.canvas_source = FigureCanvasTkAgg(self.fig_source, master=sourcePreview)
        self.canvas_source.get_tk_widget().grid(row=0, column=0, columnspan=2, sticky="nsew")

        ttk.Label(sourcePreview, text="Canvas scaling (%)")\
            .grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.canvas_scaling = ttk.Entry(sourcePreview, width=8)
        self.canvas_scaling.grid(row=1, column=1, sticky="w", pady=(6, 0), padx=(6, 0))

        

        # ---------------- Path preview ----------------
        # Status text shown above the preview while it's (re)generating -
        # generation runs synchronously, so this is set just before the
        # blocking work starts and cleared right after.
        self.preview_status = ttk.Label(
            pathPreview, text="", font=("Segoe UI", 11, "bold"), anchor="center"
        )
        self.preview_status.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self.fig_preview = figPreview        # Pass figPreview from main
        self.ax_preview = self.fig_preview.add_subplot(111)   # Create one subplot only
        self.ax_preview.set_aspect("equal")
        self.ax_preview.axis("off")
        self.canvas_preview = FigureCanvasTkAgg(self.fig_preview, master=pathPreview)
        self.canvas_preview.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        # ---------------- Controls ----------------
        r = 0
        r = self._section(controls, "General", r)

        ttk.Label(controls, text="Path generation mode")\
            .grid(row=r, column=0, sticky="w")
        self.path_mode = ttk.Combobox(
            controls, values=PATH_MODES, state="readonly"
        )
        self.path_mode.grid(row=r, column=1, sticky="ew", padx=(6, 0))
        self.path_mode.bind("<<ComboboxSelected>>", self._on_path_mode_changed)
        r += 1

        self.pen_number, r = self._entry(controls, "Pen number", r)

        self.feed_rate, r = self._entry(controls, "Layer feed rate (mm/min)", r)

        r = self._section(controls, "Visualisation", r)
        self.line_color, r = self._entry(controls, "Line color (R,G,B)", r)
        self.line_width, r = self._entry(controls, "Line width", r)

        r = self._section(controls, "Polygon controls", r)
        self.min_shell_points, r = self._entry(controls, "Min shell points", r)
        self.smoothing_tolerance, r = self._entry(controls, "Smoothing tolerance", r)
        self.max_edge_len, r = self._entry(controls, "Max edge length", r)

        # Mode-specific controls: every frame below is stacked in the same
        # grid cell and only the one matching the current path generation
        # mode is shown (see _update_mode_visibility()), so only fields
        # that are actually used by the selected mode appear.
        mode_container = ttk.Frame(controls)
        mode_container.grid(row=r, column=0, columnspan=2, sticky="new")
        mode_container.columnconfigure(0, weight=1)
        r += 1
        self.mode_frames = {}

        f, rr = self._mode_frame(mode_container, "inward_offset", "Inward offset")
        self.inward_step, rr = self._entry(f, "Step", rr)

        f, rr = self._mode_frame(mode_container, "lawnmower", "Lawnmower")
        self.lawn_spacing, rr = self._entry(f, "Track spacing", rr)
        self.lawn_angle, rr = self._entry(f, "Angle", rr)

        f, rr = self._mode_frame(mode_container, "am_fill", "AM fill")
        self.am_spacing, rr = self._entry(f, "Line spacing", rr)
        self.am_scan_angle, rr = self._entry(f, "Scan angle", rr)
        self.am_step_size, rr = self._entry(f, "Wave sample density", rr)
        self.am_envelope, rr = self._entry(f, "Envelope smoothing", rr)
        self.am_amplitude, rr = self._entry(f, "Amplitude pxl", rr)
        self.am_cycle, rr = self._entry(f, "Cycle / pixel", rr)

        f, rr = self._mode_frame(mode_container, "svg_trace", "SVG trace")
        self.svg_curve_flatness, rr = self._entry(f, "Curve flatness", rr)

        f, rr = self._mode_frame(mode_container, "foam_voronoi", "Foam Voronoi (CVT)")
        self.foam_num_points, rr = self._entry(f, "Num points", rr)
        self.foam_relaxation_iterations, rr = self._entry(f, "Relaxation iterations", rr)
        self.foam_edge_density_bias, rr = self._entry(f, "Edge density bias", rr)
        self.foam_edge_curvature, rr = self._entry(f, "Edge curvature", rr)
        self.foam_seed, rr = self._entry(f, "Seed (<=0 = random)", rr)

        f, rr = self._mode_frame(mode_container, "billiard_fill", "Billiard Bounce Fill")
        self.billiard_num_balls, rr = self._entry(f, "Num balls", rr)
        self.billiard_total_path_length, rr = self._entry(f, "Total path length (px)", rr)
        self.billiard_deflection_jitter_deg, rr = self._entry(f, "Deflection jitter (deg)", rr)
        self.billiard_coverage_bias, rr = self._entry(f, "Coverage bias (0-1)", rr)
        self.billiard_coverage_grid_resolution, rr = self._entry(f, "Coverage grid resolution", rr)
        self.billiard_seed, rr = self._entry(f, "Seed (<=0 = random)", rr)

        f, rr = self._mode_frame(mode_container, "spiral_fill", "Spiral Fill")
        self.spiral_offset_step, rr = self._entry(f, "Offset step", rr)

        f, rr = self._mode_frame(mode_container, "am_spiral_fill", "AM Spiral Fill")
        self.am_spiral_pitch, rr = self._entry(f, "Pitch", rr)
        self.am_spiral_step_size, rr = self._entry(f, "Wave sample density", rr)
        self.am_spiral_envelope, rr = self._entry(f, "Envelope smoothing", rr)
        self.am_spiral_amplitude, rr = self._entry(f, "Amplitude pxl", rr)
        self.am_spiral_cycle, rr = self._entry(f, "Cycle / pixel", rr)

        f, rr = self._mode_frame(mode_container, "dot_fill", "Dot Fill")
        self.dot_line_spacing, rr = self._entry(f, "Line spacing", rr)
        self.dot_scan_angle, rr = self._entry(f, "Scan angle", rr)
        self.dot_sample_spacing, rr = self._entry(f, "Sample spacing", rr)
        self.dot_circle_pitch, rr = self._entry(f, "Circle pitch", rr)
        self.dot_max_diameter, rr = self._entry(f, "Max dot diameter", rr)
        self.dot_circle_resolution, rr = self._entry(f, "Circle resolution", rr)

        f, rr = self._mode_frame(mode_container, "tsp_art", "TSP Art")
        self.tsp_num_points, rr = self._entry(f, "Num points", rr)
        self.tsp_darkness_bias, rr = self._entry(f, "Darkness bias (0-1)", rr)
        self.tsp_k_neighbors, rr = self._entry(f, "Optimization neighbors", rr)
        self.tsp_opt_passes, rr = self._entry(f, "Optimization passes", rr)
        self.tsp_seed, rr = self._entry(f, "Seed (<=0 = random)", rr)

        ttk.Button(controls, text="Save XML & Update View", command=self.update_preview)\
            .grid(row=r, column=0, columnspan=2, sticky="sew", pady=(10, 0))
        # Give this last row all the leftover vertical space in the panel so
        # the button always sits flush with the bottom of the window instead
        # of right after whatever fields happen to be visible above it.
        controls.rowconfigure(r, weight=1)

        self._update_mode_visibility(self.path_mode.get() or PATH_MODES[0])

    # ---------------------------------------------------------
    # Helper widgets (GRID)
    # ---------------------------------------------------------
    def _section(self, parent, title, row):
        ttk.Label(parent, text=title, font=("Segoe UI", 9, "bold"))\
            .grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
        return row + 1

    def _entry(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        e = ttk.Entry(parent)
        e.grid(row=row, column=1, sticky="ew", pady=2, padx=(6, 0))
        return e, row + 1

    def _mode_frame(self, container, key, title):
        """
        Create one mode-specific parameter group. All such frames share the
        same grid cell (row 0, col 0) inside `container` - only the frame(s)
        for the currently selected path generation mode are actually
        gridded at a time (see _update_mode_visibility()); the rest are
        grid_remove()'d, which takes them out of the layout entirely.
        """
        f = ttk.Frame(container)
        f.grid(row=0, column=0, sticky="new")
        f.columnconfigure(1, weight=1)
        self.mode_frames[key] = f
        r = self._section(f, title, 0)
        return f, r

    def _update_mode_visibility(self, mode):
        """Show only the control frame(s) relevant to `mode`, hide the rest."""
        keys_to_show = set(MODE_SECTION_KEYS.get(mode, []))
        for key, frame in self.mode_frames.items():
            if key in keys_to_show:
                frame.grid()
            else:
                frame.grid_remove()

    def _on_path_mode_changed(self, event=None):
        # Regenerate the preview first, then swap which control fields are
        # shown - doing it in this order (rather than reflowing the panel
        # immediately) avoids the fields jumping around while the person's
        # eyes are still on the "Updating preview" label / the new preview
        # coming in.
        self.update_preview()
        self._update_mode_visibility(self.path_mode.get())

    # ---------------------------------------------------------

    def change_layer(self, _):
        self.save_layer()
        self.current_layer = self.layer_select.current()
        self.load_layer(self.current_layer)

    def load_layer(self, index):
        if not self.layers:
            return
        layer = self.layers[index]

        self.source_path.delete(0, tk.END)
        self.source_path.insert(0, layer.findtext("source_path", ""))

        self.update_source_preview()

        enabled_text = layer.findtext("enabled", "true")
        self.layer_enabled.set(enabled_text.strip().lower() in ("1", "true", "yes", "on"))

        mode = layer.findtext("path_generation_mode", PATH_MODES[0])
        self._apply_source_type_constraints(mode)

        self.pen_number.delete(0, tk.END)
        self.pen_number.insert(0, layer.findtext("pen_number", "0"))

        self.feed_rate.delete(0, tk.END)
        self.feed_rate.insert(0, layer.findtext("layer_feed_rate", "0"))

        self.canvas_scaling.delete(0, tk.END)
        self.canvas_scaling.insert(0, layer.findtext("canvas_scaling", "100"))

        vis = layer.find("visualisation")
        self.line_color.delete(0, tk.END)
        self.line_color.insert(0, vis.findtext("line_color", "0,0,0"))
        self.line_width.delete(0, tk.END)
        self.line_width.insert(0, vis.findtext("line_width", "1"))

        poly = layer.find("polygon_controls")
        self.min_shell_points.delete(0, tk.END)
        self.min_shell_points.insert(0, poly.findtext("min_shell_points", "0"))
        self.smoothing_tolerance.delete(0, tk.END)
        self.smoothing_tolerance.insert(0, poly.findtext("smoothing_tolerance", "0"))
        self.max_edge_len.delete(0, tk.END)
        self.max_edge_len.insert(0, poly.findtext("max_edge_len", "0"))

        self.inward_step.delete(0, tk.END)
        self.inward_step.insert(0, layer.findtext("inward_offset/step", "0"))

        lawn = layer.find("lawnmower")
        self.lawn_spacing.delete(0, tk.END)
        self.lawn_spacing.insert(0, lawn.findtext("lawnmover_track_spacing", "0"))
        self.lawn_angle.delete(0, tk.END)
        self.lawn_angle.insert(0, lawn.findtext("angle", "0"))

        am = layer.find("am_fill")
        self.am_spacing.delete(0, tk.END)
        self.am_spacing.insert(0, am.findtext("am_line_spacing", "0"))
        self.am_scan_angle.delete(0, tk.END)
        self.am_scan_angle.insert(0, am.findtext("scan_angle_deg", "0"))
        self.am_step_size.delete(0, tk.END)
        self.am_step_size.insert(0, am.findtext("step_size", "0"))
        self.am_envelope.delete(0, tk.END)
        self.am_envelope.insert(0, am.findtext("envelope_smoothing", "0"))
        self.am_amplitude.delete(0, tk.END)
        self.am_amplitude.insert(0, am.findtext("amplitude_pxl", "0"))
        self.am_cycle.delete(0, tk.END)
        self.am_cycle.insert(0, am.findtext("cycle_per_pixel", "0"))

        svg_trace = layer.find("svg_trace")
        self.svg_curve_flatness.delete(0, tk.END)
        if svg_trace is not None:
            self.svg_curve_flatness.insert(0, svg_trace.findtext("curve_flatness", "10.0"))
        else:
            self.svg_curve_flatness.insert(0, "10.0")

        foam = layer.find("foam_voronoi")
        self.foam_num_points.delete(0, tk.END)
        self.foam_relaxation_iterations.delete(0, tk.END)
        self.foam_edge_density_bias.delete(0, tk.END)
        self.foam_edge_curvature.delete(0, tk.END)
        self.foam_seed.delete(0, tk.END)
        if foam is not None:
            self.foam_num_points.insert(0, foam.findtext("num_points", "150"))
            self.foam_relaxation_iterations.insert(0, foam.findtext("relaxation_iterations", "5"))
            self.foam_edge_density_bias.insert(0, foam.findtext("edge_density_bias", "0.0"))
            self.foam_edge_curvature.insert(0, foam.findtext("edge_curvature", "0.0"))
            self.foam_seed.insert(0, foam.findtext("seed", "42"))
        else:
            self.foam_num_points.insert(0, "150")
            self.foam_relaxation_iterations.insert(0, "5")
            self.foam_edge_density_bias.insert(0, "0.0")
            self.foam_edge_curvature.insert(0, "0.0")
            self.foam_seed.insert(0, "42")

        billiard = layer.find("billiard_fill")
        self.billiard_num_balls.delete(0, tk.END)
        self.billiard_total_path_length.delete(0, tk.END)
        self.billiard_deflection_jitter_deg.delete(0, tk.END)
        self.billiard_coverage_bias.delete(0, tk.END)
        self.billiard_coverage_grid_resolution.delete(0, tk.END)
        self.billiard_seed.delete(0, tk.END)
        if billiard is not None:
            self.billiard_num_balls.insert(0, billiard.findtext("num_balls", "1"))
            self.billiard_total_path_length.insert(0, billiard.findtext("total_path_length", "3000.0"))
            self.billiard_deflection_jitter_deg.insert(0, billiard.findtext("deflection_jitter_deg", "12.0"))
            self.billiard_coverage_bias.insert(0, billiard.findtext("coverage_bias", "0.5"))
            self.billiard_coverage_grid_resolution.insert(0, billiard.findtext("coverage_grid_resolution", "40"))
            self.billiard_seed.insert(0, billiard.findtext("seed", "42"))
        else:
            self.billiard_num_balls.insert(0, "1")
            self.billiard_total_path_length.insert(0, "3000.0")
            self.billiard_deflection_jitter_deg.insert(0, "12.0")
            self.billiard_coverage_bias.insert(0, "0.5")
            self.billiard_coverage_grid_resolution.insert(0, "40")
            self.billiard_seed.insert(0, "42")

        spiral = layer.find("spiral_fill")
        self.spiral_offset_step.delete(0, tk.END)
        if spiral is not None:
            self.spiral_offset_step.insert(0, spiral.findtext("offset_step", "6.0"))
        else:
            self.spiral_offset_step.insert(0, "6.0")

        am_spiral = layer.find("am_spiral_fill")
        self.am_spiral_pitch.delete(0, tk.END)
        self.am_spiral_step_size.delete(0, tk.END)
        self.am_spiral_envelope.delete(0, tk.END)
        self.am_spiral_amplitude.delete(0, tk.END)
        self.am_spiral_cycle.delete(0, tk.END)
        if am_spiral is not None:
            self.am_spiral_pitch.insert(0, am_spiral.findtext("pitch", "12.0"))
            self.am_spiral_step_size.insert(0, am_spiral.findtext("step_size", "0.2"))
            self.am_spiral_envelope.insert(0, am_spiral.findtext("envelope_smoothing", "3"))
            self.am_spiral_amplitude.insert(0, am_spiral.findtext("amplitude_pxl", "4"))
            self.am_spiral_cycle.insert(0, am_spiral.findtext("cycle_per_pixel", "0.2"))
        else:
            self.am_spiral_pitch.insert(0, "12.0")
            self.am_spiral_step_size.insert(0, "0.2")
            self.am_spiral_envelope.insert(0, "3")
            self.am_spiral_amplitude.insert(0, "4")
            self.am_spiral_cycle.insert(0, "0.2")

        dot = layer.find("dot_fill")
        self.dot_line_spacing.delete(0, tk.END)
        self.dot_scan_angle.delete(0, tk.END)
        self.dot_sample_spacing.delete(0, tk.END)
        self.dot_circle_pitch.delete(0, tk.END)
        self.dot_max_diameter.delete(0, tk.END)
        self.dot_circle_resolution.delete(0, tk.END)
        if dot is not None:
            self.dot_line_spacing.insert(0, dot.findtext("line_spacing", "20.0"))
            self.dot_scan_angle.insert(0, dot.findtext("scan_angle_deg", "0.0"))
            self.dot_sample_spacing.insert(0, dot.findtext("sample_spacing", "12.0"))
            self.dot_circle_pitch.insert(0, dot.findtext("circle_pitch", "2.5"))
            self.dot_max_diameter.insert(0, dot.findtext("max_diameter", "14.0"))
            self.dot_circle_resolution.insert(0, dot.findtext("circle_resolution", "10"))
        else:
            self.dot_line_spacing.insert(0, "20.0")
            self.dot_scan_angle.insert(0, "0.0")
            self.dot_sample_spacing.insert(0, "12.0")
            self.dot_circle_pitch.insert(0, "2.5")
            self.dot_max_diameter.insert(0, "14.0")
            self.dot_circle_resolution.insert(0, "10")

        tsp = layer.find("tsp_art")
        self.tsp_num_points.delete(0, tk.END)
        self.tsp_darkness_bias.delete(0, tk.END)
        self.tsp_k_neighbors.delete(0, tk.END)
        self.tsp_opt_passes.delete(0, tk.END)
        self.tsp_seed.delete(0, tk.END)
        if tsp is not None:
            self.tsp_num_points.insert(0, tsp.findtext("num_points", "600"))
            self.tsp_darkness_bias.insert(0, tsp.findtext("darkness_bias", "1.0"))
            self.tsp_k_neighbors.insert(0, tsp.findtext("k_neighbors", "8"))
            self.tsp_opt_passes.insert(0, tsp.findtext("opt_passes", "6"))
            self.tsp_seed.insert(0, tsp.findtext("seed", "42"))
        else:
            self.tsp_num_points.insert(0, "600")
            self.tsp_darkness_bias.insert(0, "1.0")
            self.tsp_k_neighbors.insert(0, "8")
            self.tsp_opt_passes.insert(0, "6")
            self.tsp_seed.insert(0, "42")

    def save_layer(self):
        if not self.layers:
            return
        layer = self.layers[self.current_layer]

        layer.find("source_path").text = self.source_path.get()
        layer.find("path_generation_mode").text = self.path_mode.get()
        layer.find("pen_number").text = self.pen_number.get()
        layer.find("layer_feed_rate").text = self.feed_rate.get()

        enabled_el = layer.find("enabled")
        if enabled_el is None:
            enabled_el = ET.SubElement(layer, "enabled")
        enabled_el.text = "true" if self.layer_enabled.get() else "false"

        canvas_scaling_el = layer.find("canvas_scaling")
        if canvas_scaling_el is None:
            canvas_scaling_el = ET.SubElement(layer, "canvas_scaling")
        canvas_scaling_el.text = self.canvas_scaling.get()

        vis = layer.find("visualisation")
        vis.find("line_color").text = self.line_color.get()
        vis.find("line_width").text = self.line_width.get()

        poly = layer.find("polygon_controls")
        poly.find("min_shell_points").text = self.min_shell_points.get()
        poly.find("smoothing_tolerance").text = self.smoothing_tolerance.get()
        poly.find("max_edge_len").text = self.max_edge_len.get()

        layer.find("inward_offset/step").text = self.inward_step.get()

        lawn = layer.find("lawnmower")
        lawn.find("lawnmover_track_spacing").text = self.lawn_spacing.get()
        lawn.find("angle").text = self.lawn_angle.get()

        am = layer.find("am_fill")
        am.find("am_line_spacing").text = self.am_spacing.get()
        am.find("scan_angle_deg").text = self.am_scan_angle.get()
        am.find("step_size").text = self.am_step_size.get()
        am.find("envelope_smoothing").text = self.am_envelope.get()
        am.find("amplitude_pxl").text = self.am_amplitude.get()
        am.find("cycle_per_pixel").text = self.am_cycle.get()

        svg_trace = layer.find("svg_trace")
        if svg_trace is None:
            svg_trace = ET.SubElement(layer, "svg_trace")
            ET.SubElement(svg_trace, "curve_flatness")
        svg_trace.find("curve_flatness").text = self.svg_curve_flatness.get()

        foam = layer.find("foam_voronoi")
        if foam is None:
            foam = ET.SubElement(layer, "foam_voronoi")
            ET.SubElement(foam, "num_points")
            ET.SubElement(foam, "relaxation_iterations")
            ET.SubElement(foam, "edge_density_bias")
            ET.SubElement(foam, "edge_curvature")
            ET.SubElement(foam, "seed")
        foam.find("num_points").text = self.foam_num_points.get()
        foam.find("relaxation_iterations").text = self.foam_relaxation_iterations.get()
        foam.find("edge_density_bias").text = self.foam_edge_density_bias.get()
        foam.find("edge_curvature").text = self.foam_edge_curvature.get()
        foam.find("seed").text = self.foam_seed.get()

        billiard = layer.find("billiard_fill")
        if billiard is None:
            billiard = ET.SubElement(layer, "billiard_fill")
            ET.SubElement(billiard, "num_balls")
            ET.SubElement(billiard, "total_path_length")
            ET.SubElement(billiard, "deflection_jitter_deg")
            ET.SubElement(billiard, "coverage_bias")
            ET.SubElement(billiard, "coverage_grid_resolution")
            ET.SubElement(billiard, "seed")
        billiard.find("num_balls").text = self.billiard_num_balls.get()
        billiard.find("total_path_length").text = self.billiard_total_path_length.get()
        billiard.find("deflection_jitter_deg").text = self.billiard_deflection_jitter_deg.get()
        billiard.find("coverage_bias").text = self.billiard_coverage_bias.get()
        billiard.find("coverage_grid_resolution").text = self.billiard_coverage_grid_resolution.get()
        billiard.find("seed").text = self.billiard_seed.get()

        spiral = layer.find("spiral_fill")
        if spiral is None:
            spiral = ET.SubElement(layer, "spiral_fill")
            ET.SubElement(spiral, "offset_step")
        spiral.find("offset_step").text = self.spiral_offset_step.get()

        am_spiral = layer.find("am_spiral_fill")
        if am_spiral is None:
            am_spiral = ET.SubElement(layer, "am_spiral_fill")
            ET.SubElement(am_spiral, "pitch")
            ET.SubElement(am_spiral, "step_size")
            ET.SubElement(am_spiral, "envelope_smoothing")
            ET.SubElement(am_spiral, "amplitude_pxl")
            ET.SubElement(am_spiral, "cycle_per_pixel")
        am_spiral.find("pitch").text = self.am_spiral_pitch.get()
        am_spiral.find("step_size").text = self.am_spiral_step_size.get()
        am_spiral.find("envelope_smoothing").text = self.am_spiral_envelope.get()
        am_spiral.find("amplitude_pxl").text = self.am_spiral_amplitude.get()
        am_spiral.find("cycle_per_pixel").text = self.am_spiral_cycle.get()

        dot = layer.find("dot_fill")
        if dot is None:
            dot = ET.SubElement(layer, "dot_fill")
            ET.SubElement(dot, "line_spacing")
            ET.SubElement(dot, "scan_angle_deg")
            ET.SubElement(dot, "sample_spacing")
            ET.SubElement(dot, "circle_pitch")
            ET.SubElement(dot, "max_diameter")
            ET.SubElement(dot, "circle_resolution")
        dot.find("line_spacing").text = self.dot_line_spacing.get()
        dot.find("scan_angle_deg").text = self.dot_scan_angle.get()
        dot.find("sample_spacing").text = self.dot_sample_spacing.get()
        dot.find("circle_pitch").text = self.dot_circle_pitch.get()
        dot.find("max_diameter").text = self.dot_max_diameter.get()
        dot.find("circle_resolution").text = self.dot_circle_resolution.get()

        tsp = layer.find("tsp_art")
        if tsp is None:
            tsp = ET.SubElement(layer, "tsp_art")
            ET.SubElement(tsp, "num_points")
            ET.SubElement(tsp, "darkness_bias")
            ET.SubElement(tsp, "k_neighbors")
            ET.SubElement(tsp, "opt_passes")
            ET.SubElement(tsp, "seed")
        tsp.find("num_points").text = self.tsp_num_points.get()
        tsp.find("darkness_bias").text = self.tsp_darkness_bias.get()
        tsp.find("k_neighbors").text = self.tsp_k_neighbors.get()
        tsp.find("opt_passes").text = self.tsp_opt_passes.get()
        tsp.find("seed").text = self.tsp_seed.get()

    def _new_default_layer_element(self):
        """Build a single <layer> element with sensible default values."""
        new_layer = ET.Element("layer")
        ET.SubElement(new_layer, "source_path").text = ""
        ET.SubElement(new_layer, "path_generation_mode").text = PATH_MODES[0]
        ET.SubElement(new_layer, "pen_number").text = "0"
        ET.SubElement(new_layer, "layer_feed_rate").text = "6000"
        ET.SubElement(new_layer, "enabled").text = "true"
        ET.SubElement(new_layer, "canvas_scaling").text = "100"

        vis = ET.SubElement(new_layer, "visualisation")
        ET.SubElement(vis, "line_color").text = "0,0,0"
        ET.SubElement(vis, "line_width").text = "2"

        poly = ET.SubElement(new_layer, "polygon_controls")
        ET.SubElement(poly, "min_shell_points").text = "6"
        ET.SubElement(poly, "smoothing_tolerance").text = "1.0"
        ET.SubElement(poly, "max_edge_len").text = "10"

        inward = ET.SubElement(new_layer, "inward_offset")
        ET.SubElement(inward, "step").text = "6"

        lawn = ET.SubElement(new_layer, "lawnmower")
        ET.SubElement(lawn, "lawnmover_track_spacing").text = "10"
        ET.SubElement(lawn, "angle").text = "45"

        am = ET.SubElement(new_layer, "am_fill")
        ET.SubElement(am, "am_line_spacing").text = "10"
        ET.SubElement(am, "scan_angle_deg").text = "0"
        ET.SubElement(am, "step_size").text = "0.2"
        ET.SubElement(am, "envelope_smoothing").text = "3"
        ET.SubElement(am, "amplitude_pxl").text = "4"
        ET.SubElement(am, "cycle_per_pixel").text = "0.2"

        svg_trace = ET.SubElement(new_layer, "svg_trace")
        ET.SubElement(svg_trace, "curve_flatness").text = "10.0"

        foam = ET.SubElement(new_layer, "foam_voronoi")
        ET.SubElement(foam, "num_points").text = "150"
        ET.SubElement(foam, "relaxation_iterations").text = "5"
        ET.SubElement(foam, "edge_density_bias").text = "0.0"
        ET.SubElement(foam, "edge_curvature").text = "0.0"
        ET.SubElement(foam, "seed").text = "42"

        billiard = ET.SubElement(new_layer, "billiard_fill")
        ET.SubElement(billiard, "num_balls").text = "1"
        ET.SubElement(billiard, "total_path_length").text = "3000.0"
        ET.SubElement(billiard, "deflection_jitter_deg").text = "12.0"
        ET.SubElement(billiard, "coverage_bias").text = "0.5"
        ET.SubElement(billiard, "coverage_grid_resolution").text = "40"
        ET.SubElement(billiard, "seed").text = "42"

        spiral = ET.SubElement(new_layer, "spiral_fill")
        ET.SubElement(spiral, "offset_step").text = "6.0"

        am_spiral = ET.SubElement(new_layer, "am_spiral_fill")
        ET.SubElement(am_spiral, "pitch").text = "12.0"
        ET.SubElement(am_spiral, "step_size").text = "0.2"
        ET.SubElement(am_spiral, "envelope_smoothing").text = "3"
        ET.SubElement(am_spiral, "amplitude_pxl").text = "4"
        ET.SubElement(am_spiral, "cycle_per_pixel").text = "0.2"

        dot = ET.SubElement(new_layer, "dot_fill")
        ET.SubElement(dot, "line_spacing").text = "20.0"
        ET.SubElement(dot, "scan_angle_deg").text = "0.0"
        ET.SubElement(dot, "sample_spacing").text = "12.0"
        ET.SubElement(dot, "circle_pitch").text = "2.5"
        ET.SubElement(dot, "max_diameter").text = "14.0"
        ET.SubElement(dot, "circle_resolution").text = "10"

        tsp = ET.SubElement(new_layer, "tsp_art")
        ET.SubElement(tsp, "num_points").text = "600"
        ET.SubElement(tsp, "darkness_bias").text = "1.0"
        ET.SubElement(tsp, "k_neighbors").text = "8"
        ET.SubElement(tsp, "opt_passes").text = "6"
        ET.SubElement(tsp, "seed").text = "42"

        return new_layer

    def _create_default_xml(self, path):
        """Write a minimal valid input_parameters.xml (one default layer) to path."""
        root_elem = ET.Element("layers")
        root_elem.append(self._new_default_layer_element())
        ET.ElementTree(root_elem).write(path)

    def add_layer(self):
        new_layer = self._new_default_layer_element()

        self.root_elem.append(new_layer)
        self.layers.append(new_layer)

        self.layer_select["values"] = list(range(1, len(self.layers) + 1))
        self.layer_select.current(len(self.layers) - 1)
        self.current_layer = len(self.layers) - 1
        self.load_layer(self.current_layer)
        self.update_preview()

    # ---------------------------------------------------------
    # Project folder selection / creation
    # ---------------------------------------------------------

    def select_project_folder(self):
        """Browse for an existing project folder and reload its XML."""
        folder = filedialog.askdirectory(
            title="Select Project Folder",
            initialdir=self.project_folder.get() or os.getcwd()
        )
        if not folder:
            return  # user cancelled -- keep current project
        self._load_project_folder(folder)

    def create_project_folder(self):
        """Create a new project folder (with a default XML) and switch to it."""
        parent = filedialog.askdirectory(
            title="Choose Location for New Project Folder",
            initialdir=self.project_folder.get() or os.getcwd()
        )
        if not parent:
            return  # user cancelled

        name = simpledialog.askstring(
            "New Project Folder",
            "Folder name:",
            parent=self.root
        )
        if not name:
            return  # user cancelled or entered nothing

        new_folder = os.path.join(parent, name)
        try:
            os.makedirs(new_folder, exist_ok=False)
        except FileExistsError:
            messagebox.showerror(
                "Folder Exists",
                f"A folder named '{name}' already exists at:\n{parent}"
            )
            return
        except OSError as e:
            messagebox.showerror("Error", f"Could not create folder:\n{e}")
            return

        self._load_project_folder(new_folder)

    def _load_project_folder(self, folder):
        """Switch the working/project folder and (re)load input_parameters.xml."""
        xml_path = os.path.join(folder, "input_parameters.xml")

        if not os.path.exists(xml_path):
            # New or empty folder -- start it off with a default XML.
            self._create_default_xml(xml_path)

        try:
            os.chdir(folder)
        except OSError as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")
            return

        # Keep xml_path relative, consistent with the rest of the app
        # (source paths, output.nc, etc. are all resolved against cwd).
        self.xml_path = "input_parameters.xml"
        self.project_folder.set(folder)
        save_last_project_folder(folder)

        try:
            self.tree = ET.parse(self.xml_path)
        except ET.ParseError as e:
            messagebox.showerror(
                "Invalid XML",
                f"Could not read '{self.xml_path}':\n{e}"
            )
            return

        self.root_elem = self.tree.getroot()
        self.layers = self.root_elem.findall("layer")

        if not self.layers:
            self.root_elem.append(self._new_default_layer_element())
            self.layers = self.root_elem.findall("layer")
            self.tree.write(self.xml_path)

        self.layer_select["values"] = list(range(1, len(self.layers) + 1))
        self.current_layer = 0
        self.layer_select.current(0)
        self.load_layer(0)
        self.update_preview()

    def remove_layer(self):
        if not self.layers:
            return
        layer = self.layers.pop(self.current_layer)
        self.root_elem.remove(layer)

        self.layer_select["values"] = list(range(1, len(self.layers) + 1))
        self.current_layer = max(0, self.current_layer - 1)
        if self.layers:
            self.layer_select.current(self.current_layer)
            self.load_layer(self.current_layer)
        self.update_preview()

    def update_preview(self):
        #self.save_layer()
        #self.tree.write(self.xml_path)
        #self.update_callback(self.xml_path)
        resetOutputFile()

        self.save_layer()
        self.tree.write(self.xml_path)

        # Let the user know path generation is running before the blocking
        # work starts below - force a redraw now since nothing else yields
        # back to the Tk event loop until generation finishes.
        self.preview_status.config(text="Updating preview")
        self.preview_status.update_idletasks()

        # Clear the axes
        self.ax_preview.cla()
        self.ax_preview.set_aspect("equal")
        self.ax_preview.axis("off")

        # Generate new preview
        from utils.preview import generate_preview_from_xml
        generate_preview_from_xml(self.xml_path, self.ax_preview)

        # Force immediate redraw
        self.canvas_preview.draw()   # Use draw() not draw_idle()

        self.preview_status.config(text="")



    def browse_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Images and SVGs", "*.png *.svg"), ("PNG images", "*.png"), ("SVG files", "*.svg")]
        )
        if path:
            self.source_path.delete(0, tk.END)
            self.source_path.insert(0, path)

            # Picking an SVG only makes sense with "trace SVG" -- force it
            # and lock the dropdown until a PNG is loaded again.
            self._apply_source_type_constraints(self.path_mode.get())

            self.update_source_preview()

    def _apply_source_type_constraints(self, desired_mode):
        """Keep path generation mode consistent with the current source file.

        SVG sources only work with "trace SVG" (see process_layer.py), so
        that mode is forced and the dropdown is locked. Any other source
        removes "trace SVG" from the selectable options entirely (it can't
        produce anything meaningful from a raster image) and falls back to
        a sane mode if it was previously stuck on "trace SVG"."""
        source = self.source_path.get()

        if source.lower().endswith(".svg"):
            self.path_mode["values"] = PATH_MODES
            self.path_mode.set("trace SVG")
            self.path_mode.configure(state="disabled")
        else:
            non_svg_modes = [m for m in PATH_MODES if m != "trace SVG"]
            self.path_mode["values"] = non_svg_modes
            self.path_mode.configure(state="readonly")
            if desired_mode in non_svg_modes:
                self.path_mode.set(desired_mode)
            else:
                self.path_mode.set(PATH_MODES[0])

        self._update_mode_visibility(self.path_mode.get())
