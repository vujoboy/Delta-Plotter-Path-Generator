from dataclasses import dataclass
from typing import Tuple
import config

ColorRGB = Tuple[int, int, int]

@dataclass
class LayerDetails:
    # Main layer info 
    source_path: str = ""
    path_generation_mode: str = config.mode_simple_contour
    pen_number: int = 0
    layer_feed_rate: int = 1000
    enabled: bool = True
    canvas_scaling: float = 100.0  # % of the canvas height the source image should be scaled to fill

    # Visualisation
    line_color: ColorRGB = (230, 100, 200)
    line_width: int = 2

    # Polygon controls
    min_shell_points: int = 8
    smoothing_tolerance: float = 1.0
    max_edge_len: float = 10.0

    # Inward offset
    step: float = 5.0

    # Lawnmower
    lawnmover_track_spacing: float = 8.0
    angle: float = 87.0

    # AM fill
    am_line_spacing: int = 12.0
    scan_angle_deg: float = 0.0
    step_size: float = 0.2
    envelope_smoothing: int = 3
    amplitude_pxl: int = 4
    cycle_per_pixel: float = 0.2

    # SVG trace
    svg_curve_flatness: float = 10.0

    # Foam Voronoi (CVT) fill
    foam_num_points: int = 150
    foam_relaxation_iterations: int = 5
    foam_edge_density_bias: float = 0.0
    foam_edge_curvature: float = 0.0
    foam_seed: int = 42  # <= 0 means "random each run"

    # Billiard bounce fill
    billiard_num_balls: int = 1
    billiard_total_path_length: float = 3000.0
    billiard_deflection_jitter_deg: float = 12.0
    billiard_coverage_bias: float = 0.5  # 0 = pure physics, 1 = always steer to least-covered ground
    billiard_coverage_grid_resolution: int = 40
    billiard_seed: int = 42  # <= 0 means "random each run"

    # Spiral fill
    spiral_offset_step: float = 6.0

    # AM spiral fill
    am_spiral_pitch: float = 12.0
    am_spiral_step_size: float = 0.2
    am_spiral_envelope_smoothing: int = 3
    am_spiral_amplitude_pxl: int = 4
    am_spiral_cycle_per_pixel: float = 0.2

    # Dot fill
    dot_line_spacing: float = 20.0
    dot_scan_angle_deg: float = 0.0
    dot_sample_spacing: float = 12.0
    dot_circle_pitch: float = 2.5
    dot_max_diameter: float = 14.0
    dot_circle_resolution: int = 10

    # TSP art
    tsp_num_points: int = 600
    tsp_darkness_bias: float = 1.0
    tsp_k_neighbors: int = 8
    tsp_opt_passes: int = 6
    tsp_seed: int = 42  # <= 0 means "random each run"