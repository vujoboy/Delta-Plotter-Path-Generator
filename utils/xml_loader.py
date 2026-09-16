import xml.etree.ElementTree as ET
from typing import Tuple
from models.layer_details import LayerDetails

def parse_color(text: str) -> Tuple[int, int, int]:
    return tuple(map(int, text.split(",")))


def parse_bool(text: str) -> bool:
    return text.strip().lower() in ("1", "true", "yes", "on")


def get_value(parent, tag, cast):
    el = parent.find(tag)
    if el is None or el.text is None:
        return None
    return cast(el.text)

def layer_from_xml(layer_el: ET.Element) -> LayerDetails:
    layer = LayerDetails()  # start with defaults

    # --- main ---
    if (v := get_value(layer_el, "source_path", str)) is not None:
        layer.source_path = v

    if (v := get_value(layer_el, "path_generation_mode", str)) is not None:
        layer.path_generation_mode = v

    if (v := get_value(layer_el, "pen_number", int)) is not None:
        layer.pen_number = v

    if (v := get_value(layer_el, "layer_feed_rate", int)) is not None:
        layer.layer_feed_rate = v

    # Older XML files won't have this tag -- default to enabled (True).
    if (v := get_value(layer_el, "enabled", parse_bool)) is not None:
        layer.enabled = v

    if (v := get_value(layer_el, "canvas_scaling", float)) is not None:
        layer.canvas_scaling = v

    # --- visualisation ---
    vis = layer_el.find("visualisation")
    if vis is not None:
        if (v := get_value(vis, "line_color", parse_color)) is not None:
            layer.line_color = v
        if (v := get_value(vis, "line_width", int)) is not None:
            layer.line_width = v

    # --- polygon controls ---
    poly = layer_el.find("polygon_controls")
    if poly is not None:
        if (v := get_value(poly, "min_shell_points", int)) is not None:
            layer.min_shell_points = v
        if (v := get_value(poly, "smoothing_tolerance", float)) is not None:
            layer.smoothing_tolerance = v
        if (v := get_value(poly, "max_edge_len", float)) is not None:
            layer.max_edge_len = v

    # --- inward offset ---
    inward = layer_el.find("inward_offset")
    if inward is not None:
        if (v := get_value(inward, "step", int)) is not None:
            layer.step = v

    # --- lawnmower ---
    lawn = layer_el.find("lawnmower")
    if lawn is not None:
        if (v := get_value(lawn, "lawnmover_track_spacing", float)) is not None:
            layer.lawnmover_track_spacing = v
        if (v := get_value(lawn, "angle", float)) is not None:
            layer.angle = v

    # --- AM fill ---
    am = layer_el.find("am_fill")
    if am is not None:
        if (v := get_value(am, "am_line_spacing", float)) is not None:
            layer.am_line_spacing = v
        if (v := get_value(am, "scan_angle_deg", float)) is not None:
            layer.scan_angle_deg = v
        if (v := get_value(am, "step_size", float)) is not None:
            layer.step_size = v
        if (v := get_value(am, "envelope_smoothing", int)) is not None:
            layer.envelope_smoothing = v
        if (v := get_value(am, "amplitude_pxl", int)) is not None:
            layer.amplitude_pxl = v
        if (v := get_value(am, "cycle_per_pixel", float)) is not None:
            layer.cycle_per_pixel = v

    # --- SVG trace ---
    svg_trace = layer_el.find("svg_trace")
    if svg_trace is not None:
        if (v := get_value(svg_trace, "curve_flatness", float)) is not None:
            layer.svg_curve_flatness = v

    # --- Foam Voronoi (CVT) fill ---
    foam = layer_el.find("foam_voronoi")
    if foam is not None:
        if (v := get_value(foam, "num_points", int)) is not None:
            layer.foam_num_points = v
        if (v := get_value(foam, "relaxation_iterations", int)) is not None:
            layer.foam_relaxation_iterations = v
        if (v := get_value(foam, "edge_density_bias", float)) is not None:
            layer.foam_edge_density_bias = v
        if (v := get_value(foam, "edge_curvature", float)) is not None:
            layer.foam_edge_curvature = v
        if (v := get_value(foam, "seed", int)) is not None:
            layer.foam_seed = v

    # --- Billiard bounce fill ---
    billiard = layer_el.find("billiard_fill")
    if billiard is not None:
        if (v := get_value(billiard, "num_balls", int)) is not None:
            layer.billiard_num_balls = v
        if (v := get_value(billiard, "total_path_length", float)) is not None:
            layer.billiard_total_path_length = v
        if (v := get_value(billiard, "deflection_jitter_deg", float)) is not None:
            layer.billiard_deflection_jitter_deg = v
        if (v := get_value(billiard, "coverage_bias", float)) is not None:
            layer.billiard_coverage_bias = v
        if (v := get_value(billiard, "coverage_grid_resolution", int)) is not None:
            layer.billiard_coverage_grid_resolution = v
        if (v := get_value(billiard, "seed", int)) is not None:
            layer.billiard_seed = v

    # --- Spiral fill ---
    spiral = layer_el.find("spiral_fill")
    if spiral is not None:
        if (v := get_value(spiral, "offset_step", float)) is not None:
            layer.spiral_offset_step = v

    # --- AM spiral fill ---
    am_spiral = layer_el.find("am_spiral_fill")
    if am_spiral is not None:
        if (v := get_value(am_spiral, "pitch", float)) is not None:
            layer.am_spiral_pitch = v
        if (v := get_value(am_spiral, "step_size", float)) is not None:
            layer.am_spiral_step_size = v
        if (v := get_value(am_spiral, "envelope_smoothing", int)) is not None:
            layer.am_spiral_envelope_smoothing = v
        if (v := get_value(am_spiral, "amplitude_pxl", int)) is not None:
            layer.am_spiral_amplitude_pxl = v
        if (v := get_value(am_spiral, "cycle_per_pixel", float)) is not None:
            layer.am_spiral_cycle_per_pixel = v

    # --- Dot fill ---
    dot = layer_el.find("dot_fill")
    if dot is not None:
        if (v := get_value(dot, "line_spacing", float)) is not None:
            layer.dot_line_spacing = v
        if (v := get_value(dot, "scan_angle_deg", float)) is not None:
            layer.dot_scan_angle_deg = v
        if (v := get_value(dot, "sample_spacing", float)) is not None:
            layer.dot_sample_spacing = v
        if (v := get_value(dot, "circle_pitch", float)) is not None:
            layer.dot_circle_pitch = v
        if (v := get_value(dot, "max_diameter", float)) is not None:
            layer.dot_max_diameter = v
        if (v := get_value(dot, "circle_resolution", int)) is not None:
            layer.dot_circle_resolution = v

    # --- TSP art ---
    tsp = layer_el.find("tsp_art")
    if tsp is not None:
        if (v := get_value(tsp, "num_points", int)) is not None:
            layer.tsp_num_points = v
        if (v := get_value(tsp, "darkness_bias", float)) is not None:
            layer.tsp_darkness_bias = v
        if (v := get_value(tsp, "k_neighbors", int)) is not None:
            layer.tsp_k_neighbors = v
        if (v := get_value(tsp, "opt_passes", int)) is not None:
            layer.tsp_opt_passes = v
        if (v := get_value(tsp, "seed", int)) is not None:
            layer.tsp_seed = v

    return layer

def load_layers_from_xml(path: str) -> list[LayerDetails]:
    tree = ET.parse(path)
    root = tree.getroot()

    layers = []
    for layer_el in root.findall("layer"):
        layers.append(layer_from_xml(layer_el))

    return layers
