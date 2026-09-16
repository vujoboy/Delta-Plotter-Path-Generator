import config
import os

from shapely.geometry import Polygon, LineString
import numpy as np
import cv2

from utils.gcode_handling import write_poligons_to_gcode, write_linepath_to_gcode, start_layer_in_gcode, end_layer_in_gcode
from utils.amplitude_modulation import generate_all_am_polylines, crop_lines_with_polygons
from utils.lawnmower_fill import break_long_edges, lawnmower_fill, generate_offsets, subdivide_line
from utils.skeletonize_lines import extract_centerline_polylines
from utils.foam_fill import generate_foam_voronoi_fill
from utils.billiard_fill import generate_billiard_fill
from utils.spiral_fill import generate_spiral_fill
from utils.am_spiral import generate_am_spiral_polyline
from utils.dot_fill import generate_dot_fill, generate_dot_fill_inside_contours
from utils.tsp_art import generate_tsp_art, generate_tsp_art_inside_contours
from dataclasses import dataclass
from typing import List, Tuple
from models.layer_details import LayerDetails

try:
    from utils.svg_tracer import trace_svg_lines
except ImportError:
    trace_svg_lines = None

Point = Tuple[float, float]
Polyline = List[Point]

@dataclass
class PlotData:
    polygons: List[Polygon] = None
    skeletons: List[Polyline] = None
    offsets: List[Polygon] = None
    lawnmower_paths: List[List[Tuple[float, float]]] = None
    am_linestrings: List[LineString] = None
    svg_lines: List[Polyline] = None
    foam_edges: List[Polyline] = None
    billiard_paths: List[Polyline] = None
    spiral_paths: List[Polyline] = None
    am_spiral_lines: List[Polyline] = None
    dot_lines: List[Polyline] = None
    tsp_art_lines: List[Polyline] = None

def process_layer(layerData: LayerDetails):


    path_generation_mode = layerData.path_generation_mode #setting defeult for startup

    # Canvas scaling: % of the canvas height the source image/SVG should
    # be scaled to fill (see config.DRWAING_AREA_HEIGHT).
    canvas_scaling = layerData.canvas_scaling

    # Poligon controls
    minShellPoints = layerData.min_shell_points
    smoothingTolearance = layerData.smoothing_tolerance
    max_edge_len = layerData.max_edge_len #longer segments will be broken so that delta kinematics transformation is correct 

    # Inward offset control parameters
    step = layerData.step

    # Lawnmover control parameters
    lawnmover_track_spacing = layerData.lawnmover_track_spacing
    angle = layerData.angle

    # AM fill control parameters
    am_line_spacing = layerData.am_line_spacing
    scan_angle_deg = layerData.scan_angle_deg
    step_size = layerData.step_size
    envelope_smoothing = layerData.envelope_smoothing
    amplitude_pxl = layerData.amplitude_pxl
    cycle_per_pixel = layerData.cycle_per_pixel

    # SVG trace control parameters
    svg_curve_flatness = layerData.svg_curve_flatness

    # Foam Voronoi (CVT) control parameters
    foam_num_points = layerData.foam_num_points
    foam_relaxation_iterations = layerData.foam_relaxation_iterations
    foam_edge_density_bias = layerData.foam_edge_density_bias
    foam_edge_curvature = layerData.foam_edge_curvature
    foam_seed = layerData.foam_seed

    # Billiard bounce fill control parameters
    billiard_num_balls = layerData.billiard_num_balls
    billiard_total_path_length = layerData.billiard_total_path_length
    billiard_deflection_jitter_deg = layerData.billiard_deflection_jitter_deg
    billiard_coverage_bias = layerData.billiard_coverage_bias
    billiard_coverage_grid_resolution = layerData.billiard_coverage_grid_resolution
    billiard_seed = layerData.billiard_seed

    # Spiral fill control parameters
    spiral_offset_step = layerData.spiral_offset_step

    # AM spiral fill control parameters
    am_spiral_pitch = layerData.am_spiral_pitch
    am_spiral_step_size = layerData.am_spiral_step_size
    am_spiral_envelope_smoothing = layerData.am_spiral_envelope_smoothing
    am_spiral_amplitude_pxl = layerData.am_spiral_amplitude_pxl
    am_spiral_cycle_per_pixel = layerData.am_spiral_cycle_per_pixel

    # Dot fill control parameters
    dot_line_spacing = layerData.dot_line_spacing
    dot_scan_angle_deg = layerData.dot_scan_angle_deg
    dot_sample_spacing = layerData.dot_sample_spacing
    dot_circle_pitch = layerData.dot_circle_pitch
    dot_max_diameter = layerData.dot_max_diameter
    dot_circle_resolution = layerData.dot_circle_resolution

    # TSP art control parameters
    tsp_num_points = layerData.tsp_num_points
    tsp_darkness_bias = layerData.tsp_darkness_bias
    tsp_k_neighbors = layerData.tsp_k_neighbors
    tsp_opt_passes = layerData.tsp_opt_passes
    tsp_seed = layerData.tsp_seed

    # File paths
    source_path = layerData.source_path

    
    # Prepare plot data payload
    plot_data = PlotData(
        polygons=[],
        skeletons=[],
        offsets=[],
        lawnmower_paths=[],
        am_linestrings=[],
        svg_lines=[],
        foam_edges=[],
        billiard_paths=[],
        spiral_paths=[],
        am_spiral_lines=[],
        dot_lines=[],
        tsp_art_lines=[]
    )

    # Functions start here
    def get_children(idx, hierarchy):
        """Return indices of all immediate children of a contour."""
        children = []
        child = hierarchy[idx][2]
        while child != -1:
            children.append(child)
            child = hierarchy[child][0]
        return children

    def contour_to_polygons(idx, contours, hierarchy, depth=0, flip=False, tol=smoothingTolearance):
        """
        Recursively build polygons. 
        If flip=True, invert the solid/hole meaning (for when outermost contour is discarded).
        """
        shell = contours[idx].squeeze()
        if shell.ndim != 2 or shell.shape[0] < 3:
            return []

        children = get_children(idx, hierarchy)
        result = []

        # Compute effective depth parity after flip
        solid_level = (depth % 2 == 0) if not flip else (depth % 2 == 1)

        if solid_level:
            # This contour is a solid shell
            holes = []
            solids_inside = []
            for c in children:
                # Child is opposite type (hole)
                holes.append(contours[c].squeeze())
                # Recursively look for islands inside the hole
                for gc in get_children(c, hierarchy):
                    solids_inside.extend(contour_to_polygons(gc, contours, hierarchy, depth + 2, flip))
            try:
                if len(shell) >= minShellPoints:
                    print("shell size " + str(len(shell)))
                    print("no. of holes " + str(len(holes)))
                    poly = Polygon(shell, [h for h in holes if h.ndim == 2 and h.shape[0] >= 3])
                    if(tol == 0):
                        result.append(poly)
                    else:
                        result.append(poly.simplify(tolerance=tol, preserve_topology=True)) #TODO fix poligon smoothing without ruining long line breaking
                    
            except Exception as e:
                print(f"Skipping invalid polygon {idx}: {e}")
            result.extend(solids_inside)

        else:
            # Hole — recurse for islands within
            for c in children:
                result.extend(contour_to_polygons(c, contours, hierarchy, depth + 1, flip))

        return result

    def removeTransparancy(img, h, w):
        whiteBackgroung = np.ones((h, w, 3), dtype=np.uint8) * 255
        # Split channels
        b, g, r, a = cv2.split(img)

        # Normalize alpha mask
        alpha = a.astype(float) / 255.0
        alpha = alpha[..., None]  # shape (h, w, 1)

        # Foreground without alpha
        fg_rgb = cv2.merge([b, g, r]).astype(float)
        whiteBackgroung = whiteBackgroung.astype(float)

        # Blend
        result = fg_rgb * alpha + whiteBackgroung * (1 - alpha)
        result = result.astype(np.uint8)
        return result

    # Functions end here

    # --> Trace SVG mode: source is a vector .svg file, not a raster image.
    # Handled entirely separately from the raster pipeline below, since there
    # is no pixel image to rasterize/threshold/contour here - the paths are
    # taken directly from the SVG geometry.
    if path_generation_mode == config.mode_trace_svg:
        if trace_svg_lines is None:
            raise ImportError(
                "The 'trace SVG' path generation mode requires the 'svgelements' "
                "package. Install it with:  pip install svgelements"
            )

        svg_lines, svg_w, svg_h = trace_svg_lines(source_path, curve_flatness=svg_curve_flatness)

        # Save canvas height into shared config file (same role IMAGE_HEIGHT_PXL
        # plays for raster sources - used by the gcode coordinate transform)
        config.IMAGE_HEIGHT_PXL = svg_h

        # Canvas dimensions the image/SVG is fit into: full width, but only
        # `canvas_scaling`% of the configured canvas height.
        effective_height_mm = config.DRWAING_AREA_HEIGHT * (canvas_scaling / 100.0)

        autoScaleFacX = config.DRWAING_AREA_LENGHT / svg_w
        autoScaleFacY = effective_height_mm / svg_h
        print('auto scale factor X: ', autoScaleFacX)
        print('auto scale factor Y: ', autoScaleFacY)
        config.AUTO_SCALE_FAC = min(autoScaleFacX, autoScaleFacY)
        print(config.AUTO_SCALE_FAC)

        config.PIXEL_PER_MM = svg_w / config.DRWAING_AREA_LENGHT if autoScaleFacX < autoScaleFacY else svg_h / effective_height_mm
        print('pixels per mm: ', config.PIXEL_PER_MM)

        print(f"Traced {len(svg_lines)} line(s) from SVG")

        # Break long straight runs into shorter segments (same max_edge_len
        # used elsewhere so the delta kinematics transform stays accurate)
        svg_lines = [subdivide_line(line, max_edge_len) for line in svg_lines]

        config.FEED = layerData.layer_feed_rate
        start_layer_in_gcode()

        plot_data.svg_lines.extend(svg_lines)

        # Write traced lines to G-code
        for line in svg_lines:
            write_linepath_to_gcode(line, svg_h)

        end_layer_in_gcode()

        return plot_data

    # Open image from disk and load it in openCV
    if not source_path or not os.path.isfile(source_path):
        # No source image selected yet (e.g. a brand-new layer in a
        # freshly-created project) - nothing to render. Return the
        # already-initialized, empty plot_data instead of crashing.
        end_layer_in_gcode()
        return plot_data

    img = cv2.imread(source_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        # Path existed but OpenCV couldn't decode it (corrupt file, wrong
        # format, etc.) - same graceful fallback rather than crashing on
        # the next line's img.shape.
        end_layer_in_gcode()
        return plot_data
    h, w, c = img.shape
    img = removeTransparancy(img, h, w)
    # Save image height (h) into shared config file
    config.IMAGE_HEIGHT_PXL = h

    # Paint the pixels on the edge (iwards border) white
    cv2.line(img, (0, 0), (0, h-1), (255, 255, 255) , 1)
    cv2.line(img, (0, 0), (w-1, 0), (255, 255, 255) , 1)
    cv2.line(img, (0, h-1), (w-1, h-1), (255, 255, 255) , 1)
    cv2.line(img, (w-1, 0), (w-1, h-1), (255, 255, 255) , 1)

    # Canvas dimensions the image is fit into: full width, but only
    # `canvas_scaling`% of the configured canvas height.
    effective_height_mm = config.DRWAING_AREA_HEIGHT * (canvas_scaling / 100.0)

    autoScaleFacX = config.DRWAING_AREA_LENGHT / w
    autoScaleFacY = effective_height_mm / h
    print('auto scale factor X: ', autoScaleFacX)
    print('auto scale factor Y: ', autoScaleFacY)
    config.AUTO_SCALE_FAC = min(autoScaleFacX, autoScaleFacY)
    print(config.AUTO_SCALE_FAC)

    ppmm = None
    if(autoScaleFacX < autoScaleFacY):
        ppmm = w / config.DRWAING_AREA_LENGHT
    else:
        ppmm = h / effective_height_mm
    config.PIXEL_PER_MM = ppmm
    print('pixels per mm: ', ppmm)

    # Segment image
    imgray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, thresh = cv2.threshold(imgray, 240, 255, 0) # 2nd parameter controls threshold, 254 captures faint gray, 1 only captures black as contour

    # Find contours of the segmented image
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    # NOTE: contours are intentionally NOT drawn onto `img` here - `img` is
    # the same array every raster-sampling fill mode (AM fill, AM spiral
    # fill, dot fill, TSP art, skeletonize) reads pixel brightness from
    # afterward. Burning contour outlines into it first used to leave a
    # dark red seam wherever a contour was found - including internal
    # contours like a highlight's boundary in the middle of an otherwise
    # light area - which darkness-driven fills would then render as an
    # oversized feature exactly there. If a contour-overlay preview is
    # ever needed again, draw it onto `white_image` (below) or a fresh
    # copy of `img`, never onto `img` itself.

    #create white image and also draw on white image
    white_image = np.ones((h, w, 3), dtype=np.uint8) * 255
    cv2.drawContours(white_image, contours, -1, (0, 0, 255)) #-1 for all contours

    #disp_img_1 = cv2.resize(img, (w, h))
    #cv2.imshow('Image_fill_1', img) # Uncomment this line to show contours over original image

    # Scaling image so that the display size is the same as on the plotter (on a specific monitor)
    imgRescaled = cv2.resize(img, (int(w * config.AUTO_SCALE_FAC * 6.35), int(h * config.AUTO_SCALE_FAC * 6.35)))
    #cv2.imshow('Real size image', imgRescaled) # UNCOMMENT TO SHOW REAL SIZE WINDOW

    print("number of contours = " + str(len(contours)))

    # Build all contour polygons
    hierarchy = hierarchy[0]

    polygons = []
    for i in range(len(contours)):
        if hierarchy[i][3] == -1:  # top-level contour (outermost)
            # discard its own shape, but flip interpretation for its children
            for c in get_children(i, hierarchy):
                polygons.extend(contour_to_polygons(c, contours, hierarchy, depth=0, flip=False, tol=smoothingTolearance))


    print(f"Extracted {len(polygons)} polygons (including nested islands)")
    polygons = [break_long_edges(p, max_edge_len) for p in polygons]

    # Choosing what paths to generate
    all_offsets = []
    config.FEED = layerData.layer_feed_rate
    start_layer_in_gcode()

    # --> Simple contour mode
    if path_generation_mode == config.mode_simple_contour:
        # Plot contours
        for poly in polygons:
            if poly.geom_type == "Polygon":
                polys = [poly]
            else:  # MultiPolygon
                polys = list(poly.geoms)
            plot_data.polygons.extend(polys)

        # Write contour polygons to gcode
        write_poligons_to_gcode(polygons, h)

    # --> Inward offset mode
    if path_generation_mode == config.mode_inward_offset_fill:
        # Generate offsets for all polygons
        for poly in polygons:
            generate_offsets(poly, step, all_offsets)

            all_offsets = [break_long_edges(p, max_edge_len) for p in all_offsets]

            print("Length of polygons list " + str(len(polygons)))
            print("Length of all_offsets list " + str(len(all_offsets)))

            # Plotting offsets
            for poly in all_offsets:
                if poly.geom_type == "Polygon":
                    polys = [poly]
                else:  # MultiPolygon
                    polys = list(poly.geoms)

                # Exterior
                plot_data.offsets.extend(polys)
                # Holes in red
                # plot_data.offsets.extend(poly.interiors)

        # Write offset infill polygons to gcode
        write_poligons_to_gcode(all_offsets, h)

    # --> Lawnmover infill mode
    if path_generation_mode == config.mode_lawnmover_fill:
        # Generate lawnmover infill
        all_lawnmower_paths = []

        for i, poly in enumerate(polygons):
            path, clipped = lawnmower_fill(poly, lawnmover_track_spacing, angle, max_segment_length=max_edge_len)
            all_lawnmower_paths.append(path)

        # Plot lawnmover infill
        for paths in all_lawnmower_paths:
            plot_data.lawnmower_paths.extend(paths)

        # Lawnmover infill write to gcode
        if len(polygons) > 0:
            for poly in polygons:
                paths, multi = lawnmower_fill(poly, lawnmover_track_spacing, angle, max_segment_length=max_edge_len)
                # Write them to G-code:
                for p in paths:
                    write_linepath_to_gcode(p, h)

    # --> Skeletonized lines
    if path_generation_mode == config.mode_skeletonized_lines:
        # Generate skeletonized lines

        skeleton_polylines = extract_centerline_polylines(img)

        # Plot skeletons
        #for paths in skeleton_polylines:
        #    plot_data.skeletons.extend(paths)
        plot_data.skeletons.extend(skeleton_polylines)

        # Write them to G-code:
        for line in skeleton_polylines:
            write_linepath_to_gcode(line, h)

    # --> AM fill
    if path_generation_mode == config.mode_AM_fill_full_canvas or path_generation_mode == config.mode_AM_fill_inside_contours:
        am_polylines = []

        am_polylines = generate_all_am_polylines(img, angle_deg=scan_angle_deg,
                                        am_line_spacing=am_line_spacing,
                                        step_size=step_size, envelope_smoothing_strength=envelope_smoothing,
                                        am_amplitude=amplitude_pxl, cyc_per_pix=cycle_per_pixel)

        # Convert AM polylines to linestrings (for possibility of trimming)
        am_linestrings = []
        for polyline in am_polylines:
            am_linestrings.append(LineString(polyline))

        if path_generation_mode == config.mode_AM_fill_inside_contours:
            # --> AM fill inside contours
            cropped_am_linestrings = crop_lines_with_polygons(am_linestrings, polygons)
            plot_data.am_linestrings.extend(cropped_am_linestrings)

            # Write cropped AM lines to gcode
            for path in cropped_am_linestrings:
                write_linepath_to_gcode(list(path.coords), h)

        elif path_generation_mode == config.mode_AM_fill_full_canvas:
            # --> AM fill entire canvas
            plot_data.am_linestrings.extend(am_linestrings)

            # Write full AM lines to gcode
            for path in am_polylines:
                write_linepath_to_gcode(path, h)

    # --> Foam Voronoi (relaxed/CVT Voronoi) fill
    if path_generation_mode == config.mode_foam_voronoi:
        all_foam_edges = []

        for poly in polygons:
            polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
            for p in polys:
                edges = generate_foam_voronoi_fill(
                    p,
                    num_points=foam_num_points,
                    relaxation_iterations=foam_relaxation_iterations,
                    edge_density_bias=foam_edge_density_bias,
                    edge_curvature=foam_edge_curvature,
                    seed=(foam_seed if foam_seed and foam_seed > 0 else None),
                    max_edge_len=max_edge_len,
                )
                all_foam_edges.extend(edges)

        print(f"Generated {len(all_foam_edges)} foam cell edges")

        plot_data.foam_edges.extend(all_foam_edges)

        # Write foam cell edges to gcode
        for edge in all_foam_edges:
            write_linepath_to_gcode(edge, h)

    # --> Billiard bounce fill
    if path_generation_mode == config.mode_billiard_fill:
        all_billiard_paths = []

        for poly in polygons:
            polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
            for p in polys:
                paths = generate_billiard_fill(
                    p,
                    num_balls=billiard_num_balls,
                    total_path_length=billiard_total_path_length,
                    deflection_jitter_deg=billiard_deflection_jitter_deg,
                    coverage_bias=billiard_coverage_bias,
                    coverage_grid_resolution=billiard_coverage_grid_resolution,
                    seed=(billiard_seed if billiard_seed and billiard_seed > 0 else None),
                    max_edge_len=max_edge_len,
                )
                all_billiard_paths.extend(paths)

        print(f"Generated {len(all_billiard_paths)} billiard ball path(s)")

        plot_data.billiard_paths.extend(all_billiard_paths)

        # Write ball trajectories to gcode
        for path in all_billiard_paths:
            write_linepath_to_gcode(path, h)

    # --> Spiral fill
    if path_generation_mode == config.mode_spiral_fill:
        all_spiral_paths = []

        for poly in polygons:
            polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
            for p in polys:
                paths = generate_spiral_fill(
                    p,
                    offset_step=spiral_offset_step,
                    max_edge_len=max_edge_len,
                )
                all_spiral_paths.extend(paths)

        print(f"Generated {len(all_spiral_paths)} spiral(s)")

        plot_data.spiral_paths.extend(all_spiral_paths)

        # Write spiral strokes to gcode
        for path in all_spiral_paths:
            write_linepath_to_gcode(path, h)

    # --> AM spiral fill
    if path_generation_mode == config.mode_AM_spiral_fill_full_canvas \
            or path_generation_mode == config.mode_AM_spiral_fill_inside_contours:
        am_spiral_polyline = generate_am_spiral_polyline(
            img, pitch=am_spiral_pitch, sampling_density=am_spiral_step_size,
            envelope_smoothing_strength=am_spiral_envelope_smoothing,
            amplitude=am_spiral_amplitude_pxl, cyc_per_pix=am_spiral_cycle_per_pixel,
        )

        if path_generation_mode == config.mode_AM_spiral_fill_inside_contours:
            crop_targets = polygons
        else:
            # Full canvas: the spiral's own radius reaches past the canvas
            # corners (a circle has to overshoot a rectangle's edges to
            # cover its corners at all) - clip it back to the canvas
            # rectangle so every point stays inside the plotter's valid
            # coordinate range, same as every other mode's output does.
            crop_targets = [Polygon([(0, 0), (w, 0), (w, h), (0, h)])]

        cropped_am_spiral_lines = crop_lines_with_polygons(
            [LineString(am_spiral_polyline)], crop_targets
        ) if len(am_spiral_polyline) >= 2 else []
        plot_data.am_spiral_lines.extend(cropped_am_spiral_lines)

        # Write AM spiral segments to gcode
        for path in cropped_am_spiral_lines:
            write_linepath_to_gcode(list(path.coords), h)

    # --> Dot fill
    if path_generation_mode == config.mode_dot_fill_full_canvas \
            or path_generation_mode == config.mode_dot_fill_inside_contours:
        if path_generation_mode == config.mode_dot_fill_inside_contours:
            dot_lines = generate_dot_fill_inside_contours(
                img, angle_deg=dot_scan_angle_deg, line_spacing=dot_line_spacing,
                sample_spacing=dot_sample_spacing, circle_pitch=dot_circle_pitch,
                max_diameter=dot_max_diameter, polygons=polygons,
                circle_resolution=dot_circle_resolution,
            )
        else:
            dot_lines = generate_dot_fill(
                img, angle_deg=dot_scan_angle_deg, line_spacing=dot_line_spacing,
                sample_spacing=dot_sample_spacing, circle_pitch=dot_circle_pitch,
                max_diameter=dot_max_diameter,
                circle_resolution=dot_circle_resolution,
            )

        print(f"Generated {len(dot_lines)} dot fill scanline(s)")

        plot_data.dot_lines.extend(dot_lines)

        # Write dot fill scanlines to gcode
        for line in dot_lines:
            write_linepath_to_gcode(line, h)

    # --> TSP art
    if path_generation_mode == config.mode_tsp_art_full_canvas \
            or path_generation_mode == config.mode_tsp_art_inside_contours:
        if path_generation_mode == config.mode_tsp_art_inside_contours:
            tsp_art_lines = generate_tsp_art_inside_contours(
                img, num_points=tsp_num_points, polygons=polygons,
                darkness_bias=tsp_darkness_bias, k_neighbors=tsp_k_neighbors,
                opt_passes=tsp_opt_passes, seed=(tsp_seed if tsp_seed and tsp_seed > 0 else None),
                max_edge_len=max_edge_len,
            )
        else:
            tsp_art_lines = generate_tsp_art(
                img, num_points=tsp_num_points,
                darkness_bias=tsp_darkness_bias, k_neighbors=tsp_k_neighbors,
                opt_passes=tsp_opt_passes, seed=(tsp_seed if tsp_seed and tsp_seed > 0 else None),
                max_edge_len=max_edge_len,
            )

        print(f"Generated {len(tsp_art_lines)} TSP art tour(s)")

        plot_data.tsp_art_lines.extend(tsp_art_lines)

        # Write TSP art tour(s) to gcode
        for line in tsp_art_lines:
            write_linepath_to_gcode(line, h)

    end_layer_in_gcode()

    return plot_data
   