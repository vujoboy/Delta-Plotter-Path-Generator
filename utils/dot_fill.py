"""
Dot fill.

Parallel scan lines are laid across the canvas (same idea as AM fill: an
angle and a line spacing). Along each scan line, sample points are spread
out at a fixed spacing, and at each one a small dot is drawn whose outer
diameter is proportional to how dark the source image is at that point
(white -> no dot, black -> the full configured diameter). Each dot is
filled with concentric offset circles (radius = pitch, 2*pitch, ... up to
the dot's own diameter) rather than a continuous spiral - every one of
those rings, and the short radial hop connecting it to the next, starts
and ends exactly on the scan line's own direction, so the whole dot stays
pen-down and the straight run to the next dot always continues cleanly
along the line.

Each scan line is emitted as ONE continuous polyline:

    edge -> [straight lead-in] -> dot -> [straight transition] -> dot
          -> ... -> dot -> [straight lead-out] -> edge

with no pen lifts anywhere within a line - not between a dot's own rings,
and not between one dot and the next - and the line starts/ends exactly on
the canvas border (or, for the "inside contours" variant, on the contour
boundary - see generate_dot_fill_inside_contours()).
"""

import math

import numpy as np
import cv2
from shapely.geometry import Point, LineString
from shapely.ops import unary_union


def _to_gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img


def _sample_darkness(img_gray, x, y):
    """Bilinear-sampled darkness (0 = white, 1 = black) at a single (x, y) point."""
    h, w = img_gray.shape
    x = min(max(x, 0.0), w - 1.0001)
    y = min(max(y, 0.0), h - 1.0001)
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    x1, y1 = x0 + 1, y0 + 1
    dx, dy = x - x0, y - y0

    v00 = float(img_gray[y0, x0])
    v10 = float(img_gray[y0, x1])
    v01 = float(img_gray[y1, x0])
    v11 = float(img_gray[y1, x1])

    value = v00 * (1 - dx) * (1 - dy) + v10 * dx * (1 - dy) + v01 * (1 - dx) * dy + v11 * dx * dy
    return max(0.0, min(1.0, (255.0 - value) / 255.0))


def _scanline_endpoints(w, h, angle_deg, spacing):
    """
    Border-to-border (start, end) points for every parallel scan line across
    a w x h canvas at the given angle and spacing - same technique used for
    the regular AM fill's scan lines.
    """
    if spacing <= 0:
        return []

    angle_rad = math.radians(angle_deg)
    dx, dy = math.cos(angle_rad), math.sin(angle_rad)
    px, py = -dy, dx  # direction perpendicular to the scan direction

    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    projections = [cx * px + cy * py for cx, cy in corners]
    min_proj, max_proj = min(projections), max(projections)

    num_lines = max(1, int(math.ceil((max_proj - min_proj) / spacing)))
    padding = 2
    borders = [
        ((padding, padding), (w, padding)),
        ((w - padding, padding), (w - padding, h - padding)),
        ((w - padding, h - padding), (padding, h - padding)),
        ((padding, h - padding), (padding, padding)),
    ]

    lines = []
    for i in range(num_lines + 1):
        offset = min_proj + i * (max_proj - min_proj) / num_lines
        ox, oy = offset * px, offset * py

        intersections = []
        for (bx1, by1), (bx2, by2) in borders:
            denom = dx * (by2 - by1) - dy * (bx2 - bx1)
            if denom == 0:
                continue
            t = ((bx1 - ox) * (by2 - by1) - (by1 - oy) * (bx2 - bx1)) / denom
            u = ((bx1 - ox) * dy - (by1 - oy) * dx) / denom
            if 0 <= u <= 1:
                intersections.append((ox + t * dx, oy + t * dy))

        if len(intersections) < 2:
            continue

        dists = [math.hypot(ix - ox, iy - oy) for ix, iy in intersections]
        order = sorted(range(len(intersections)), key=lambda k: dists[k])
        lines.append((intersections[order[0]], intersections[order[-1]]))

    return lines


def _dot_offset_circle_points(center, outer_radius, pitch, forward_angle, circle_resolution=10):
    """
    Points for one dot: concentric offset circles evenly spaced from the
    center out to `outer_radius`. The ring count is chosen so the spacing
    between rings comes out as close as possible to `pitch` while staying
    perfectly even across all of them (including the last one) - the dot
    always reaches its exact target size, so a naive fixed step of `pitch`
    would otherwise leave an uneven leftover gap on the last ring. First
    point is `center` itself.

    Every ring - and the short radial hop that connects it to the next one
    - starts and ends at the same point: center + radius along the scan
    line's forward direction. That keeps every hop (ring-to-ring, and the
    final exit toward the next dot) a plain straight continuation of the
    scan line itself.

    `circle_resolution` is how many straight segments approximate one full
    revolution of a ring - higher gives a rounder circle at the cost of
    more points.
    """
    if outer_radius <= 0 or pitch <= 0:
        return [center]

    angular_step = 2 * math.pi / max(int(circle_resolution), 3)

    cx, cy = center
    fdx, fdy = math.cos(forward_angle), math.sin(forward_angle)

    num_rings = max(1, round(outer_radius / pitch))
    ring_spacing = outer_radius / num_rings
    radii = [ring_spacing * i for i in range(1, num_rings + 1)]

    pts = [center]
    for radius in radii:
        ring_point = (cx + fdx * radius, cy + fdy * radius)
        pts.append(ring_point)  # straight radial hop out to this ring

        theta = 0.0
        while theta < 2 * math.pi:
            theta = min(theta + angular_step, 2 * math.pi)
            a = forward_angle + theta
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))

    return pts


def create_dot_scanline(img_gray, start_point, end_point, sample_spacing,
                         circle_pitch, max_diameter, room_fn, circle_resolution=10, min_radius_px=0.35):
    """Build one scan line's full single-stroke polyline (lead-in, dots, transitions, lead-out)."""
    length = math.hypot(end_point[0] - start_point[0], end_point[1] - start_point[1])
    if length < 1e-6 or sample_spacing <= 0:
        return [start_point, end_point]

    dx = (end_point[0] - start_point[0]) / length
    dy = (end_point[1] - start_point[1]) / length
    forward_angle = math.atan2(dy, dx)
    max_radius = max(max_diameter, 0.0) / 2.0

    stroke = [start_point]
    t = sample_spacing
    while t < length:
        cx = start_point[0] + dx * t
        cy = start_point[1] + dy * t

        stroke.append((cx, cy))  # straight transition/lead-in to this dot's center

        darkness = _sample_darkness(img_gray, cx, cy)
        outer_radius = darkness * max_radius
        # Never let a dot's rings reach past the canvas edge or (for the
        # inside-contours variant) past the contour boundary - clamp to
        # whatever room is actually available at this point instead of
        # drawing it full-size and clipping afterwards (clipping an
        # already self-overlapping polyline against a boundary is prone to
        # shattering into a huge number of tiny fragments).
        outer_radius = min(outer_radius, max(room_fn(cx, cy), 0.0))
        if outer_radius > min_radius_px:
            shape_pts = _dot_offset_circle_points(
                (cx, cy), outer_radius, circle_pitch, forward_angle, circle_resolution
            )
            stroke.extend(shape_pts[1:])  # shape_pts[0] duplicates the center already appended

        t += sample_spacing

    stroke.append(end_point)  # lead-out to the far edge
    return stroke


def _canvas_room_fn(canvas_size):
    canvas_w, canvas_h = canvas_size

    def room_fn(x, y):
        return min(x, canvas_w - x, y, canvas_h - y)

    return room_fn


def generate_dot_fill(img, angle_deg, line_spacing, sample_spacing, circle_pitch, max_diameter,
                       circle_resolution=10):
    """
    Generate the dot fill scan lines across the whole image canvas.

    Returns a list of polylines, one per scan line, each a single
    continuous stroke from one canvas edge to the other.
    """
    h, w = img.shape[:2]
    img_gray = _to_gray(img)
    room_fn = _canvas_room_fn((w, h))

    polylines = []
    for start_point, end_point in _scanline_endpoints(w, h, angle_deg, line_spacing):
        stroke = create_dot_scanline(
            img_gray, start_point, end_point, sample_spacing, circle_pitch, max_diameter,
            room_fn, circle_resolution
        )
        if len(stroke) >= 2:
            polylines.append(stroke)

    return polylines


def _split_line_by_polygons(start_point, end_point, polygons_union):
    """
    Intersect the straight segment start_point -> end_point with
    `polygons_union`, returning the (sub_start, sub_end) pairs for the
    portions that fall inside it, ordered along the original line.
    """
    line = LineString([start_point, end_point])
    clipped = line.intersection(polygons_union)
    if clipped.is_empty:
        return []

    pieces = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
    segments = []
    for piece in pieces:
        if piece.is_empty or piece.geom_type != "LineString":
            continue
        coords = list(piece.coords)
        if len(coords) >= 2:
            segments.append((coords[0], coords[-1]))

    segments.sort(key=lambda seg: math.hypot(seg[0][0] - start_point[0], seg[0][1] - start_point[1]))
    return segments


def generate_dot_fill_inside_contours(img, angle_deg, line_spacing, sample_spacing,
                                       circle_pitch, max_diameter, polygons, circle_resolution=10):
    """
    Generate the dot fill scan lines, cropped to `polygons` (same idea as
    AM fill "inside contours"): each scan line is first clipped to the
    portions that actually fall inside the contours, and each surviving
    portion becomes its own single continuous stroke - lead-in and lead-out
    now sit exactly on the contour boundary instead of the canvas edge, and
    dots are also kept from bulging past that boundary.
    """
    h, w = img.shape[:2]
    img_gray = _to_gray(img)
    if not polygons:
        return []

    union = unary_union(polygons)
    if union.is_empty:
        return []

    canvas_room_fn = _canvas_room_fn((w, h))
    boundary = union.boundary

    def room_fn(x, y):
        return min(canvas_room_fn(x, y), boundary.distance(Point(x, y)))

    polylines = []
    for start_point, end_point in _scanline_endpoints(w, h, angle_deg, line_spacing):
        for sub_start, sub_end in _split_line_by_polygons(start_point, end_point, union):
            stroke = create_dot_scanline(
                img_gray, sub_start, sub_end, sample_spacing, circle_pitch, max_diameter,
                room_fn, circle_resolution
            )
            if len(stroke) >= 2:
                polylines.append(stroke)

    return polylines
