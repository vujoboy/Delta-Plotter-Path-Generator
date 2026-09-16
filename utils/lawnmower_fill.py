from shapely.geometry import Polygon, MultiPolygon, LinearRing, LineString, MultiLineString
from shapely import affinity
import numpy as np
import math
import config

def subdivide_coords_list(coords, max_length, eps=1e-9):
    """
    Robust subdivision of a ring (coords can be closed or open).
    - Always processes the closing segment for closed rings.
    - Uses an epsilon and >= logic to avoid floating-point misses.
    - Does not round during computation (round only if you want).
    Returns a list of coords; if input was closed, output is closed (last==first).
    """
    if max_length <= 0:
        return list(coords)

    pts = [tuple(p) for p in coords]
    if len(pts) < 2:
        return pts[:]

    # Determine closedness via LinearRing (robust)
    closed = LinearRing(pts).is_ring
    if closed and (pts[0] == pts[-1]):
        pts = pts[:-1]  # drop duplicate endpoint, we'll re-close later

    n = len(pts)
    out = []

    for i in range(n):
        p0 = np.array(pts[i], dtype=float)

        # choose p1: wrap if closed; otherwise only if next exists
        if closed:
            p1 = np.array(pts[(i + 1) % n], dtype=float)
        else:
            if i + 1 < n:
                p1 = np.array(pts[i + 1], dtype=float)
            else:
                p1 = None

        out.append((float(p0[0]), float(p0[1])))

        if p1 is None:
            break

        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        seg_len = math.hypot(dx, dy)

        # use >= with small eps to avoid float misses
        if seg_len + eps >= max_length:
            parts = max(1, int(math.ceil(seg_len / max_length)))
            # insert intermediate points (exclude endpoints)
            for k in range(1, parts):
                t = k / float(parts)
                xi = p0[0] + dx * t
                yi = p0[1] + dy * t
                out.append((float(xi), float(yi)))

    # re-close if necessary
    if closed:
        if out[0] != out[-1]:
            out.append(out[0])

    # remove exact consecutive duplicates
    cleaned = [out[0]]
    for p in out[1:]:
        if p != cleaned[-1]:
            cleaned.append(p)

    if closed and cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])

    return cleaned

def subdivide_line(coords, max_length):
    """
    Subdivide a line so that no segment between points exceeds max_length.
    coords: list of (x, y) tuples
    max_length: maximum allowed segment length
    returns: new list of (x, y) tuples
    """
    if len(coords) < 2:
        return coords[:]  # nothing to subdivide

    new_coords = [coords[0]]

    for i in range(1, len(coords)):
        x1, y1 = new_coords[-1]
        x2, y2 = coords[i]

        dx = x2 - x1
        dy = y2 - y1
        seg_len = math.hypot(dx, dy)

        if seg_len <= max_length:
            new_coords.append((x2, y2))
            continue

        # number of subdivisions
        n = int(seg_len // max_length)
        step_x = dx / (n + 1)
        step_y = dy / (n + 1)

        # create intermediate points
        for k in range(1, n + 1):
            new_coords.append((x1 + k * step_x, y1 + k * step_y))

        new_coords.append((x2, y2))

    return new_coords

def break_long_edges(geom, max_length, eps=1e-9):
    """
    Subdivide polygon edges so no straight edge segment is longer than max_length.
    Works for Polygon and MultiPolygon.
    """
    if max_length <= 0 or geom.is_empty:
        return geom

    if geom.geom_type == "Polygon":
        shell_coords = list(geom.exterior.coords)
        new_shell = subdivide_coords_list(shell_coords, max_length, eps)

        new_interiors = []
        for interior in geom.interiors:
            i_coords = list(interior.coords)
            new_i = subdivide_coords_list(i_coords, max_length, eps)
            if len(new_i) >= 4:  # must have at least 3 distinct points + closing
                new_interiors.append(new_i)

        try:
            new_poly = Polygon(new_shell, new_interiors)
            if not new_poly.is_valid or new_poly.is_empty:
                return geom
            return new_poly
        except Exception:
            return geom

    elif geom.geom_type == "MultiPolygon":
        parts = [break_long_edges(p, max_length, eps) for p in geom.geoms]
        return MultiPolygon(parts)
    
    elif geom.geom_type == "LineString":
        new_coords = subdivide_line(list(geom.coords), max_length)
        return LineString(new_coords)

    elif geom.geom_type == "MultiLineString":
        new_lines = [subdivide_line(ls, max_length) for ls in geom.geoms]
        return MultiLineString(new_lines)

    else:
        return geom
    
def lawnmower_fill(geom, spacing, angle_deg=0.0, max_segment_length=10, extend=1000.0):
    """
    Create a lawnmower (parallel raster) fill for a Polygon or MultiPolygon.
    - geom: shapely.geometry.Polygon or MultiPolygon
    - spacing: distance between adjacent passes (same units as geom)
    - angle_deg: travel angle in degrees (0 = horizontal lines in XY)
    - max_segment_length: if provided, will call break_long_edges on each returned segment
    - extend: how far to extend the sweep lines beyond bbox (to ensure full intersections)
    Returns:
      ordered_paths: list of paths, where each path is a list of (x,y) tuples (open polyline)
      multiline: shapely.geometry.MultiLineString combining all segments (unsorted)
    Notes:
      - The result is ordered in a boustrophedon pattern (alternating direction each row).
      - Holes are respected because we intersect lines with the polygon.
    """
    if geom.is_empty:
        return [], MultiLineString([])
    
    #infill_margin = 0.4 #round(config.PIXEL_PER_MM * 0.5) #to create a 0.5 mm marin between outline and infill edge
    #geom = geom.buffer(-infill_margin, join_style=2) #TODO if needed fix margin generation

    # Work on each polygon part if MultiPolygon
    parts = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)

    all_segments = []   # collect shapely LineString segments in original coordinates
    ordered_rows = []   # collect per-row lists (in rotated frame), to be ordered as boustrophedon

    for part in parts:
        # rotate the polygon so we can create *horizontal* lines and then rotate back
        rot_part = affinity.rotate(part, -angle_deg, origin='centroid', use_radians=False)

        minx, miny, maxx, maxy = rot_part.bounds
        # create y positions (include a margin beyond bounds)
        y_start = miny - spacing
        y_end = maxy + spacing
        # use np.arange to generate rows in increasing order
        ys = np.arange(y_start, y_end + spacing * 0.5, spacing)

        # center origin for rotating back
        origin = rot_part.centroid.coords[0]

        for yi in ys:
            # create a long horizontal line at y=yi
            line = LineString([(minx - extend, yi), (maxx + extend, yi)])
            inter = rot_part.intersection(line)

            if inter.is_empty:
                continue

            # intersection may be LineString or MultiLineString or GeometryCollection containing lines
            segments = []
            if isinstance(inter, LineString):
                segments = [inter]
            elif isinstance(inter, MultiLineString):
                segments = list(inter.geoms)
            else:
                # try to extract lines from geometry collection-like
                for g in getattr(inter, "geoms", []):
                    if isinstance(g, LineString):
                        segments.append(g)

            # sort segments left->right in rotated frame by their centroid x
            segs_sorted = sorted(segments, key=lambda s: s.centroid.x)

            # convert to lists of coords (in rotated frame), then rotate them back to original frame
            row_coords = []
            for seg in segs_sorted:
                seg_back = affinity.rotate(seg, angle_deg, origin=origin, use_radians=False)
                if max_segment_length:
                    # optionally break long edges using provided helper if available
                    try:
                        seg_back = break_long_edges(seg_back, max_segment_length)
                    except Exception:
                        pass
                # we expect seg_back to be LineString or MultiLineString (if subdivided)
                if isinstance(seg_back, LineString):
                    row_coords.append(list(seg_back.coords))
                    all_segments.append(seg_back)
                elif isinstance(seg_back, MultiLineString):
                    for sub in seg_back.geoms:
                        row_coords.append(list(sub.coords))
                        all_segments.append(sub)

            if row_coords:
                ordered_rows.append(row_coords)

    # Now flatten ordered_rows into an ordered boustrophedon list:
    ordered_paths = []
    row_index = 0
    for row in ordered_rows:
        # row is a list of segments (left-to-right). We'll traverse them left->right on even rows,
        # and right->left on odd rows to make continuous boustrophedon path.
        if row_index % 2 == 0:
            # even row: append segments in order; each segment stays as-is
            for seg_coords in row:
                ordered_paths.append(seg_coords)
        else:
            # odd row: reverse order of segments and reverse each segment coordinate order
            for seg_coords in reversed(row):
                ordered_paths.append(list(reversed(seg_coords)))
        row_index += 1

    # Combine all segments into a MultiLineString (unordered)
    multiline = MultiLineString([LineString(s) for s in all_segments]) if all_segments else MultiLineString([])

    return ordered_paths, multiline

def generate_offsets(polygon, step, offsets):
    """Generates inward offsets while keeping holes intact (Shapely 2.x)."""
    first_offset_polygon = polygon.buffer(-step, join_style=2) # Perform 1st offset to not add contours as offsets. Accepted integer values are 1 (round), 2 (mitre), and 3 (bevel))
    stack = [first_offset_polygon]
    
    while stack:
        current = stack.pop()
        if current.is_empty:
            continue
        
        # Handle MultiPolygon
        if current.geom_type == "MultiPolygon":
            stack.extend(current.geoms)
            continue
        
        # Save current polygon
        offsets.append(current)
        
        # Shrink polygon while preserving holes (Shapely 2.x default)
        shrunk = current.buffer(-step, join_style=2) # Accepted integer values are 1 (round), 2 (mitre), and 3 (bevel)
        if not shrunk.is_empty:
            stack.append(shrunk)