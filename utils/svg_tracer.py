"""
SVG tracing utilities.

Turns an arbitrary input SVG (paths, rects, circles, ellipses, polygons,
polylines, lines - including nested <g> transforms) into a flat list of
polylines that the rest of the pipeline can treat exactly like the
skeletonized-lines / lawnmower / AM-fill polyline outputs.

Curves (cubic/quadratic beziers, arcs) are flattened to short straight
segments based on their arc length, so curve quality is controlled by a
single "curve_flatness" parameter (smaller = smoother curves, more points).

Requires the third-party 'svgelements' package:
    pip install svgelements
"""

try:
    from svgelements import SVG, Path, Shape, Move, Close, Line
    _SVGELEMENTS_AVAILABLE = True
except ImportError:
    _SVGELEMENTS_AVAILABLE = False


def _to_float(value):
    """Best-effort conversion of an svgelements Length/number to a plain float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    for attr in ("value", "amount"):
        candidate = getattr(value, attr, None)
        if candidate is None:
            continue
        try:
            return float(candidate() if callable(candidate) else candidate)
        except (TypeError, ValueError):
            continue
    return None


def _xy(point):
    """Return (x, y) for an svgelements Point, tolerating older complex-based versions."""
    if point is None:
        return None
    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))
    # Very old svgelements versions represented points as complex numbers
    try:
        return (point.real, point.imag)
    except AttributeError:
        return None


def _flatten_segment(segment, curve_flatness):
    """
    Return the list of points that approximate `segment`, NOT including its
    start point (the caller is expected to already be tracking that).
    """
    if isinstance(segment, Move):
        return []

    if isinstance(segment, (Line, Close)):
        end = _xy(segment.end)
        return [end] if end is not None else []

    # Curved segment (CubicBezier, QuadraticBezier, Arc, ...): sample it
    # based on its arc length so the chord error stays roughly constant.
    try:
        length = segment.length(error=1e-2, min_depth=3)
    except Exception:
        length = None

    if not length or length <= 0:
        end = _xy(segment.end)
        return [end] if end is not None else []

    steps = max(2, int(length / max(curve_flatness, 1e-3)))
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        try:
            pt = _xy(segment.point(t))
        except Exception:
            continue
        if pt is not None:
            points.append(pt)
    return points


def trace_svg_lines(svg_path, curve_flatness=10.0, min_points=2):
    """
    Parse an SVG file and flatten every path/shape it contains into
    polylines.

    Args:
        svg_path: path to the .svg file on disk.
        curve_flatness: max chord length (in SVG user units) used when
            sampling curved segments. Smaller = smoother curves, more points.
        min_points: polylines shorter than this are dropped.

    Returns:
        (polylines, width, height)
        polylines: List[List[(x, y)]] - open polylines, y increases downward
            (same convention as the raster pipeline), origin at (0, 0).
        width, height: size of the SVG canvas in the same coordinate space
            as the polyline points (used for auto-scaling to the plot bed,
            exactly like image width/height is used for PNG sources).
    """
    if not _SVGELEMENTS_AVAILABLE:
        raise ImportError(
            "The 'trace SVG' path generation mode requires the 'svgelements' "
            "package. Install it with:  pip install svgelements"
        )

    svg = SVG.parse(svg_path)

    polylines = []

    for element in svg.elements():
        try:
            if getattr(element, "values", None):
                if str(element.values.get("display", "")).strip().lower() == "none":
                    continue

            if isinstance(element, Shape) and not isinstance(element, Path):
                element = Path(element)

            if not isinstance(element, Path) or len(element) == 0:
                continue

            current = []
            for segment in element:
                if isinstance(segment, Move):
                    if len(current) >= min_points:
                        polylines.append(current)
                    start = _xy(segment.end)
                    current = [start] if start is not None else []
                    continue
                current.extend(_flatten_segment(segment, curve_flatness))

            if len(current) >= min_points:
                polylines.append(current)
        except Exception as e:
            print(f"Skipping unsupported SVG element ({type(element).__name__}): {e}")

    # Work out the canvas size in the same coordinate space as the traced
    # points, so it can be auto-scaled to the plot bed the same way a PNG's
    # pixel width/height is used.
    width = _to_float(getattr(svg, "width", None))
    height = _to_float(getattr(svg, "height", None))

    offset_x = offset_y = 0.0
    if width is None or height is None:
        # Fall back to the bounding box of the traced geometry itself.
        xs = [p[0] for line in polylines for p in line]
        ys = [p[1] for line in polylines for p in line]
        if xs and ys:
            offset_x, offset_y = min(xs), min(ys)
            width = max(xs) - offset_x
            height = max(ys) - offset_y
        else:
            width = width or 1.0
            height = height or 1.0

    if offset_x or offset_y:
        polylines = [[(x - offset_x, y - offset_y) for x, y in line] for line in polylines]

    if not width:
        width = 1.0
    if not height:
        height = 1.0

    return polylines, width, height
