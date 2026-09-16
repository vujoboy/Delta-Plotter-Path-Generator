"""
Spiral fill.

Starting from a contour's own perimeter, this generates a single
continuous inward spiral: repeatedly offset the polygon inward by a fixed
step (the same idea as "inward offset fill" - a classic parallel/concentric
offset), but instead of drawing each offset ring as a separate closed loop
with a pen lift in between, bridge consecutive rings together with a short
connecting segment so the whole fill draws as one continuous spiraling
stroke.

If, partway through shrinking, the material splits into more than one
piece (e.g. a horseshoe-shaped contour, or a hole squeezing a ring in two),
each piece continues on as its own independent spiral - so a layer with
several separate contours, or a single contour that breaks apart while
shrinking, still ends up fully covered, just as more than one spiral.
"""

import math

from utils.lawnmower_fill import subdivide_line


def _offset_pieces(geom, min_area):
    """Normalize a buffer() result into a list of non-degenerate Polygons."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > min_area else []
    if geom.geom_type == "MultiPolygon":
        return [g for g in geom.geoms if g.area > min_area]
    if hasattr(geom, "geoms"):  # e.g. GeometryCollection from a degenerate buffer
        return [g for g in geom.geoms if g.geom_type == "Polygon" and g.area > min_area]
    return []


def _closest_point_on_ring(ring, pt):
    """
    Nearest point to `pt` lying anywhere on the closed ring `ring` (a list
    of coordinates with ring[0] == ring[-1]).

    Returns (segment_index, projected_point), where segment_index is the i
    such that the projection falls between ring[i] and ring[i + 1].
    """
    best = None
    for i in range(len(ring) - 1):
        ax, ay = ring[i]
        bx, by = ring[i + 1]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        t = 0.0 if seg_len2 < 1e-12 else ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / seg_len2
        t = max(0.0, min(1.0, t))
        proj = (ax + dx * t, ay + dy * t)
        d = math.hypot(pt[0] - proj[0], pt[1] - proj[1])
        if best is None or d < best[0]:
            best = (d, i, proj)
    return best[1], best[2]


def _ring_loop_from(ring, seg_index, start_pt):
    """
    Walk the closed ring `ring` once all the way around, starting and
    ending at `start_pt` (a point lying on the edge ring[seg_index] ->
    ring[seg_index + 1]).
    """
    n = len(ring) - 1  # unique vertex count (ring is closed: ring[0] == ring[-1])
    loop = [start_pt]
    idx = (seg_index + 1) % n
    for _ in range(n):
        loop.append(ring[idx])
        idx = (idx + 1) % n
    loop.append(start_pt)
    return loop


def generate_spiral_fill(polygon, offset_step, max_edge_len=None):
    """
    Generate one or more continuous inward-spiral strokes filling
    `polygon` (holes are respected via shapely's own offset/erosion).

    Returns a list of polylines - normally just one continuous spiral
    starting at the contour's own perimeter and winding inward, but more
    than one if the shape splits apart while shrinking.
    """
    if polygon is None or polygon.is_empty or offset_step <= 0:
        return []

    min_area = max((offset_step * offset_step) * 0.05, 1e-9)
    if polygon.area <= min_area:
        return []

    strokes = []
    stack = [polygon]

    while stack:
        region = stack.pop()
        pieces = _offset_pieces(region, min_area)
        if not pieces:
            continue
        pieces.sort(key=lambda g: g.area, reverse=True)
        current = pieces[0]
        for extra in pieces[1:]:
            stack.append(extra)

        stroke = []
        bridge_pt = None

        while current is not None:
            ring = list(current.exterior.coords)  # closed: ring[0] == ring[-1]
            if len(ring) < 4:
                break

            if bridge_pt is None:
                loop = ring  # first (outermost) ring: trace as-is, no bridge needed
                stroke.extend(loop)
            else:
                seg_index, proj = _closest_point_on_ring(ring, bridge_pt)
                loop = _ring_loop_from(ring, seg_index, proj)
                stroke.append(proj)      # the bridge segment: bridge_pt -> proj
                stroke.extend(loop[1:])  # loop[0] duplicates proj, already added

            bridge_pt = loop[-1]  # == loop[0], the loop's closing point

            nxt = current.buffer(-offset_step, join_style=2)
            pieces = _offset_pieces(nxt, min_area)
            if not pieces:
                current = None
                continue
            pieces.sort(key=lambda g: g.area, reverse=True)
            current = pieces[0]
            for extra in pieces[1:]:
                stack.append(extra)

        if len(stroke) >= 2:
            if max_edge_len:
                stroke = subdivide_line(stroke, max_edge_len)
            strokes.append(stroke)

    return strokes
