"""
TSP art.

Scatter stipple points across the image with density weighted by darkness
(dark areas get many closely-packed points, light areas get few, sparse
ones), then connect every point into a single continuous tour - built with
a greedy nearest-neighbor construction and improved with neighbor-limited
2-opt - so the whole picture is drawn as one unbroken line whose local
density reads as tone, the way classic "TSP art" pieces work.

Only the standard library, numpy, scipy (cKDTree), shapely (already a
project dependency) and cv2 are used.
"""

import math
import random

import numpy as np
import cv2
from scipy.spatial import cKDTree
from shapely.geometry import Point, LineString
from shapely.prepared import prep
from shapely.ops import unary_union

from utils.lawnmower_fill import subdivide_line


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


# ---------------------------------------------------------------------
# 1. Darkness-weighted point scatter
# ---------------------------------------------------------------------

def _radius_shape(darkness, darkness_bias, min_ratio, max_ratio):
    """
    Local spacing as a multiple of a not-yet-known base unit ("base=1"),
    purely as a function of local darkness - used both for the actual
    sampling radius (once scaled by the calibrated base) and, unscaled,
    to calibrate that base against the target point count.
    """
    uniform = (min_ratio + max_ratio) / 2.0
    if darkness_bias <= 0:
        return uniform
    weighted = max_ratio - (max_ratio - min_ratio) * darkness
    return (1.0 - darkness_bias) * uniform + darkness_bias * weighted


def _calibrate_base_spacing(img_gray, contains_fn, bounds, num_points, darkness_bias,
                             min_ratio=0.4, max_ratio=2.5, packing=0.65, mc_samples=3000, seed=0):
    """
    Monte-Carlo calibration of the base spacing unit so that sampling at
    radius = base * _radius_shape(...) yields approximately `num_points`
    points, regardless of the image's actual tone distribution or how much
    of the bounding box `contains_fn` actually accepts (e.g. an irregular
    contour's bounding box is mostly NOT inside the contour).

    Poisson-disk point count scales as ~ packing * area / radius^2, and
    since radius = base * f(x, y) here, this reduces to solving for `base`
    from a Monte-Carlo estimate of mean(1 / f(x, y)^2) over the valid
    region.
    """
    minx, miny, maxx, maxy = bounds
    bbox_area = max((maxx - minx) * (maxy - miny), 1e-9)
    if num_points <= 0 or bbox_area <= 0:
        return 0.0

    rng = random.Random(seed)
    total_inv_f2 = 0.0
    hits = 0
    for _ in range(mc_samples):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if not contains_fn(x, y):
            continue
        d = _sample_darkness(img_gray, x, y)
        f = max(_radius_shape(d, darkness_bias, min_ratio, max_ratio), 1e-6)
        total_inv_f2 += 1.0 / (f * f)
        hits += 1

    if hits == 0:
        return 0.0

    valid_area = bbox_area * hits / mc_samples
    mean_inv_f2 = total_inv_f2 / hits
    base_sq = packing * valid_area * mean_inv_f2 / num_points
    return math.sqrt(max(base_sq, 1e-9))


def _weighted_poisson_disk_sample(img_gray, contains_fn, bounds, num_points, darkness_bias=1.0,
                                   min_ratio=0.4, max_ratio=2.5, seed=None, k=30, max_points=None):
    """
    Bridson-style Poisson-disk sampling across `bounds` (restricted to
    wherever `contains_fn` accepts), with a spacing that shrinks in dark
    areas and grows in light ones.

    darkness_bias:
        0.0 -> ignore the image, uniform spacing everywhere - a plain even
               stipple grid.
        1.0 -> spacing fully driven by local darkness (denser in black,
               sparser in white) - the standard TSP-art look.
    """
    minx, miny, maxx, maxy = bounds
    if maxx <= minx or maxy <= miny or num_points <= 0:
        return []

    base = _calibrate_base_spacing(
        img_gray, contains_fn, bounds, num_points, darkness_bias, min_ratio, max_ratio
    )
    if base <= 0:
        return []

    min_spacing = base * min_ratio
    max_spacing = base * max_ratio

    def local_radius(x, y):
        d = _sample_darkness(img_gray, x, y)
        return base * _radius_shape(d, darkness_bias, min_ratio, max_ratio)

    rng = random.Random(seed)
    cell_size = max(min_spacing / math.sqrt(2), 1e-3)
    grid_w = int(math.ceil((maxx - minx) / cell_size)) + 1
    grid_h = int(math.ceil((maxy - miny) / cell_size)) + 1
    grid = {}
    samples = []
    radii = []
    active = []

    def grid_coords(pt):
        return int((pt[0] - minx) / cell_size), int((pt[1] - miny) / cell_size)

    def fits(pt, pt_r):
        gx, gy = grid_coords(pt)
        span = int(math.ceil(max_spacing / cell_size)) + 1
        for ix in range(max(0, gx - span), min(grid_w, gx + span + 1)):
            for iy in range(max(0, gy - span), min(grid_h, gy + span + 1)):
                idx = grid.get((ix, iy))
                if idx is None:
                    continue
                ox, oy = samples[idx]
                min_dist = max(pt_r, radii[idx])
                if math.hypot(pt[0] - ox, pt[1] - oy) < min_dist:
                    return False
        return True

    for _ in range(2000):
        x0, y0 = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if contains_fn(x0, y0):
            samples.append((x0, y0))
            radii.append(local_radius(x0, y0))
            grid[grid_coords((x0, y0))] = 0
            active.append(0)
            break
    else:
        return []

    while active:
        i = rng.randrange(len(active))
        sample_idx = active[i]
        ax, ay = samples[sample_idx]
        r0 = radii[sample_idx]
        placed = False
        for _ in range(k):
            ang = rng.uniform(0, 2 * math.pi)
            rad = rng.uniform(r0, 2 * r0)
            nx, ny = ax + rad * math.cos(ang), ay + rad * math.sin(ang)
            if nx < minx or nx > maxx or ny < miny or ny > maxy:
                continue
            if not contains_fn(nx, ny):
                continue
            nr = local_radius(nx, ny)
            if fits((nx, ny), nr):
                samples.append((nx, ny))
                radii.append(nr)
                grid[grid_coords((nx, ny))] = len(samples) - 1
                active.append(len(samples) - 1)
                placed = True
                if max_points and len(samples) >= max_points:
                    return samples
                break
        if not placed:
            active.pop(i)

    if len(samples) > num_points:
        idx = rng.sample(range(len(samples)), num_points)
        samples = [samples[i] for i in idx]

    return samples


# ---------------------------------------------------------------------
# 2. Nearest-neighbor initial tour
# ---------------------------------------------------------------------

def _nearest_neighbor_tour(points, seed=None):
    """Greedy nearest-unvisited-neighbor construction, using a KD-tree with an expanding query radius."""
    n = len(points)
    if n <= 2:
        return list(range(n))

    tree = cKDTree(points)
    rng = random.Random(seed)
    start = rng.randrange(n)
    visited = np.zeros(n, dtype=bool)
    tour = [start]
    visited[start] = True
    current = start

    for _ in range(n - 1):
        k = 8
        found = None
        while found is None:
            k = min(k, n)
            _, idxs = tree.query(points[current], k=k)
            idxs = np.atleast_1d(idxs)
            for idx in idxs:
                if not visited[idx]:
                    found = int(idx)
                    break
            if found is not None or k >= n:
                break
            k *= 4
        if found is None:
            remaining = np.where(~visited)[0]
            d2 = np.hypot(points[remaining, 0] - points[current][0], points[remaining, 1] - points[current][1])
            found = int(remaining[np.argmin(d2)])
        visited[found] = True
        tour.append(found)
        current = found

    return tour


# ---------------------------------------------------------------------
# 3. Neighbor-list 2-opt improvement (open path, not a closed loop)
# ---------------------------------------------------------------------

def _two_opt_improve(points, tour, k_neighbors=8, max_passes=6):
    """
    Neighbor-limited 2-opt improvement of an open-path tour: for each edge
    (a, b), only tries swaps against a's spatially-nearest few points
    rather than every other city, which keeps this practical well beyond
    a thousand points.
    """
    n = len(tour)
    if n < 4:
        return tour

    tree = cKDTree(points)
    _, neighbor_idx = tree.query(points, k=min(k_neighbors + 1, n))

    pos = [0] * n
    for i, city in enumerate(tour):
        pos[city] = i

    def dist(i, j):
        return math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])

    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(n - 1):
            a, b = tour[i], tour[i + 1]
            dab = dist(a, b)
            for c in neighbor_idx[a]:
                c = int(c)
                if c == a or c == b:
                    continue
                j = pos[c]
                if j <= i or j + 1 >= n:
                    continue
                d_city = tour[j + 1]
                if d_city == a:
                    continue
                if dist(a, c) + dist(b, d_city) < dab + dist(c, d_city) - 1e-9:
                    tour[i + 1:j + 1] = tour[i + 1:j + 1][::-1]
                    for p in range(i + 1, j + 1):
                        pos[tour[p]] = p
                    improved = True
                    b = tour[i + 1]
                    dab = dist(a, b)

    return tour


def _build_and_improve_tour(points, k_neighbors, max_passes, seed):
    points_arr = np.array(points)
    tour = _nearest_neighbor_tour(points_arr, seed=seed)
    tour = _two_opt_improve(points_arr, tour, k_neighbors=k_neighbors, max_passes=max(0, int(max_passes)))
    return [tuple(points_arr[i]) for i in tour]


# ---------------------------------------------------------------------
# 4. Splitting the tour at jumps (so they become pen-up travel moves)
# ---------------------------------------------------------------------

# A tour edge is treated as a jump - not something to draw - when it is longer
# than this many times the local point spacing (see _split_tour_at_jumps()).
JUMP_SPACING_FACTOR = 2.5
# "Local point spacing" at a point = distance to its Nth-nearest neighbor.
JUMP_SPACING_NEIGHBOR = 6
# Tolerance (px) when testing whether an edge stays inside the shape, so edges
# that merely graze the outline between two boundary points aren't cut.
JUMP_INSIDE_TOLERANCE = 1.0


def _split_tour_at_jumps(tour_points, inside_region=None):
    """
    Split a tour (a list of points visited in order) into separate strokes
    wherever a tour edge is a jump rather than part of the drawing.

    A nearest-neighbor tour inevitably runs out of unvisited points nearby
    now and then and has to leap to a far-away leftover point; 2-opt only
    partly repairs that. Left as-is those leaps get drawn as long straight
    lines. Cutting the tour there makes each leap a pen-up travel move
    instead (each returned polyline is drawn pen-down to pen-up).

    An edge is cut when:
      - it is much longer than the local point spacing (a leap), or
      - `inside_region` is given and the edge leaves it (e.g. cuts across
        empty space between two lobes of a concave contour).

    Returns a list of polylines, each with at least 2 points.
    """
    n = len(tour_points)
    if n < 2:
        return []

    pts = np.asarray(tour_points, dtype=float)

    # Local spacing at each point: distance to its Nth-nearest neighbor.
    k = min(JUMP_SPACING_NEIGHBOR + 1, n)   # +1: the nearest "neighbor" is the point itself
    dists, _ = cKDTree(pts).query(pts, k=k)
    local_spacing = np.atleast_2d(dists)[:, -1] if k > 1 else np.zeros(n)

    strokes = []
    current = [tuple(pts[0])]
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        edge_len = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        limit = JUMP_SPACING_FACTOR * max(local_spacing[i], local_spacing[i + 1])

        is_jump = edge_len > limit
        if not is_jump and inside_region is not None:
            is_jump = not inside_region.covers(LineString([tuple(a), tuple(b)]))

        if is_jump:
            if len(current) >= 2:
                strokes.append(current)
            current = [tuple(b)]
        else:
            current.append(tuple(b))

    if len(current) >= 2:
        strokes.append(current)
    return strokes


# ---------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------

def generate_tsp_art_inside_contours(img, num_points, polygons, darkness_bias=1.0, k_neighbors=8,
                                      opt_passes=6, seed=None, max_edge_len=None):
    """
    Generate TSP art restricted to `polygons`. Each disjoint (unconnected)
    piece of the contour union gets its own independent stipple scatter and
    tour - so two separate shapes on the canvas don't end up with one tour
    containing a single long pointless jump connecting them - with the
    point budget split between pieces in proportion to their area.

    The tour is split into several strokes wherever one of its edges is a
    jump rather than part of the drawing - much longer than the local point
    spacing, or crossing outside the shape (e.g. across a narrow "waist" of
    a concave contour). Those gaps become pen-up travel moves, so the result
    is a list of polylines per piece rather than a single one.
    """
    h, w = img.shape[:2]
    if num_points <= 1:
        return []
    img_gray = _to_gray(img)

    if not polygons:
        return []

    union = unary_union(polygons)
    if union.is_empty:
        return []

    pieces = [union] if union.geom_type == "Polygon" else \
        [g for g in union.geoms if g.geom_type == "Polygon" and g.area > 1e-9]
    if not pieces:
        return []

    total_area = sum(p.area for p in pieces) or 1.0

    polylines = []
    for i, piece in enumerate(pieces):
        piece_target = max(3, round(num_points * piece.area / total_area))
        prepared = prep(piece)

        def contains_fn(x, y, _prepared=prepared):
            return _prepared.contains(Point(x, y))

        piece_seed = None if seed is None else seed + i
        points = _weighted_poisson_disk_sample(
            img_gray, contains_fn, piece.bounds, piece_target, darkness_bias, seed=piece_seed
        )
        if len(points) < 2:
            continue

        tour = _build_and_improve_tour(points, k_neighbors, opt_passes, piece_seed)

        # Leaps across the canvas / out of the shape must not be drawn: split
        # the tour there so they become pen-up travel moves.
        inside_region = prep(piece.buffer(JUMP_INSIDE_TOLERANCE))
        for stroke in _split_tour_at_jumps(tour, inside_region):
            if max_edge_len:
                stroke = subdivide_line(stroke, max_edge_len)
            polylines.append(stroke)

    return polylines
