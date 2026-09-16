"""
Billiard-bounce fill.

A "ball" is launched from a random point inside the contour polygon in a
random direction. It travels in a straight line until it hits a wall (the
contour's exterior boundary, or the boundary of a hole), reflects off that
wall like a real billiard ball, and keeps going until it has covered the
requested total travel distance. The full bounced trajectory is recorded
and used as the drawn path - this reproduces the criss-crossing "billiard
lines" look.

Two things are added on top of plain physical bouncing:

1. Deflection jitter - at each bounce a small random angle is added on top
   of the pure mirror reflection, so the ball doesn't fall into a short
   repeating loop (which a perfectly elastic bounce easily can, e.g. in a
   rectangle).

2. Coverage evening - a low-resolution grid over the contour's bounding box
   keeps a running tally of how much path has already crossed each cell.
   At each bounce, with probability `coverage_bias` the ball looks a short
   distance ahead along a handful of candidate directions (the physical
   reflection +/- the jitter spread) and steers toward whichever candidate
   points into the least-covered ground, instead of picking a random
   deflection. `coverage_bias` is the single knob:
       0.0 -> pure physics + random jitter, no coverage-awareness at all.
       1.0 -> the ball always steers toward the least-covered direction
              available at every bounce.
   Multiple balls (num_balls) share the same coverage grid, so later balls
   are steered away from ground earlier balls already walked over -- which
   is what actually spreads the fill out evenly across the shape.
"""

import math
import random

import numpy as np
from shapely.geometry import Point

from utils.lawnmower_fill import subdivide_line

EPS = 1e-9

# How many candidate deflection angles to evaluate when steering by coverage.
_NUM_COVERAGE_CANDIDATES = 9


# ---------------------------------------------------------------------
# Ray / polygon-with-holes intersection (exact reflection, no sub-stepping)
# ---------------------------------------------------------------------

def _polygon_rings(polygon):
    """Exterior + interior (hole) rings as plain coordinate lists, open (no repeated closing point)."""
    rings = [list(polygon.exterior.coords)[:-1]]
    for interior in polygon.interiors:
        rings.append(list(interior.coords)[:-1])
    return rings


def _nearest_ring_hit(origin, direction, ring):
    """Nearest intersection of a ray with one closed ring, or None."""
    ox, oy = origin
    dx, dy = direction
    best_t = None
    best_normal = None
    n = len(ring)

    for i in range(n):
        p1 = ring[i]
        p2 = ring[(i + 1) % n]
        ex, ey = p2[0] - p1[0], p2[1] - p1[1]

        denom = dx * ey - dy * ex
        if abs(denom) < EPS:
            continue  # parallel to this edge

        qx, qy = p1[0] - ox, p1[1] - oy
        t = (qx * ey - qy * ex) / denom
        u = (qx * dy - qy * dx) / denom

        if t > EPS and -EPS <= u <= 1.0 + EPS:
            if best_t is None or t < best_t:
                nx, ny = -ey, ex
                length = math.hypot(nx, ny)
                if length < EPS:
                    continue
                nx, ny = nx / length, ny / length
                if nx * dx + ny * dy > 0:  # keep normal facing back at the ray
                    nx, ny = -nx, -ny
                best_t = t
                best_normal = (nx, ny)

    if best_t is None:
        return None
    return best_t, best_normal


def _nearest_polygon_hit(origin, direction, rings):
    """Nearest intersection across the exterior and every hole ring."""
    best = None
    for ring in rings:
        hit = _nearest_ring_hit(origin, direction, ring)
        if hit is not None and (best is None or hit[0] < best[0]):
            best = hit
    return best


# ---------------------------------------------------------------------
# Coverage grid
# ---------------------------------------------------------------------

def _grid_cell(minx, miny, cell_size, gw, gh, pt):
    gx = int((pt[0] - minx) / cell_size)
    gy = int((pt[1] - miny) / cell_size)
    gx = min(max(gx, 0), gw - 1)
    gy = min(max(gy, 0), gh - 1)
    return gx, gy


def _mark_coverage(grid, minx, miny, cell_size, gw, gh, p1, p2):
    """Walk the segment p1->p2 and increment every grid cell it passes through."""
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    steps = max(1, int(length / (cell_size * 0.5)))
    for i in range(steps + 1):
        t = i / steps
        x = p1[0] + (p2[0] - p1[0]) * t
        y = p1[1] + (p2[1] - p1[1]) * t
        gx, gy = _grid_cell(minx, miny, cell_size, gw, gh, (x, y))
        grid[gy, gx] += 1.0


def _coverage_ahead(grid, minx, miny, cell_size, gw, gh, origin, direction, lookahead):
    """Sum of coverage counts in cells crossed by a short look-ahead ray (cheap, no wall check)."""
    steps = max(1, int(lookahead / (cell_size * 0.5)))
    total = 0.0
    for i in range(1, steps + 1):
        t = lookahead * i / steps
        x = origin[0] + direction[0] * t
        y = origin[1] + direction[1] * t
        gx = int((x - minx) / cell_size)
        gy = int((y - miny) / cell_size)
        if 0 <= gx < gw and 0 <= gy < gh:
            total += grid[gy, gx]
    return total


# ---------------------------------------------------------------------
# Single-ball trajectory
# ---------------------------------------------------------------------

def _compute_ball_trajectory(rings, start, direction, total_length, jitter_deg,
                              coverage_bias, grid, minx, miny, cell_size, gw, gh,
                              lookahead, rng, max_bounces=20000):
    path = [start]
    pos = start
    d = direction
    remaining = total_length
    bounces = 0

    while remaining > EPS and bounces < max_bounces:
        hit = _nearest_polygon_hit(pos, d, rings)
        if hit is None:
            break  # shouldn't happen inside a closed contour, but bail out cleanly

        t, normal = hit
        travel = min(t, remaining)
        new_pos = (pos[0] + d[0] * travel, pos[1] + d[1] * travel)
        _mark_coverage(grid, minx, miny, cell_size, gw, gh, pos, new_pos)
        path.append(new_pos)
        remaining -= travel
        bounces += 1

        if travel < t - EPS:
            break  # used up the total travel budget before reaching a wall

        # Physical mirror reflection: r = d - 2*(d.n)*n
        dot = d[0] * normal[0] + d[1] * normal[1]
        rx = d[0] - 2 * dot * normal[0]
        ry = d[1] - 2 * dot * normal[1]
        base_angle = math.atan2(ry, rx)

        origin = (new_pos[0] + normal[0] * 1.0, new_pos[1] + normal[1] * 1.0)

        if coverage_bias > 0 and rng.random() < coverage_bias:
            # Steer toward whichever nearby direction (within the jitter
            # cone around the true reflection) points into the least
            # walked-over ground so far.
            best_angle, best_score = None, None
            for k in range(_NUM_COVERAGE_CANDIDATES):
                spread = -jitter_deg + (2 * jitter_deg * k / (_NUM_COVERAGE_CANDIDATES - 1)
                                         if _NUM_COVERAGE_CANDIDATES > 1 else 0.0)
                cand_angle = base_angle + math.radians(spread)
                cand_dir = (math.cos(cand_angle), math.sin(cand_angle))
                score = _coverage_ahead(grid, minx, miny, cell_size, gw, gh, origin, cand_dir, lookahead)
                if best_score is None or score < best_score:
                    best_score, best_angle = score, cand_angle
            angle = best_angle
        else:
            angle = base_angle + math.radians(rng.uniform(-jitter_deg, jitter_deg))

        d = (math.cos(angle), math.sin(angle))
        pos = origin
        path[-1] = pos

    return path


def _random_point_in_polygon(polygon, rng, max_tries=1000):
    minx, miny, maxx, maxy = polygon.bounds
    for _ in range(max_tries):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if polygon.contains(Point(x, y)):
            return (x, y)
    return None


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def generate_billiard_fill(polygon, num_balls=1, total_path_length=3000.0,
                            deflection_jitter_deg=12.0, coverage_bias=0.5,
                            coverage_grid_resolution=40, seed=None, max_edge_len=None):
    """
    Generate one or more bounced-ball trajectories filling `polygon`.

    Returns a list of polylines (each a list of (x, y) tuples), one per
    ball, ready to hand to write_linepath_to_gcode/plotting.
    """
    if polygon is None or polygon.is_empty or num_balls <= 0 or total_path_length <= 0:
        return []

    minx, miny, maxx, maxy = polygon.bounds
    if maxx <= minx or maxy <= miny:
        return []

    # The contour we're handed has usually already been subdivided
    # (break_long_edges) into many short, collinear segments for the delta
    # kinematics G-code transform - that's irrelevant (and expensive) for
    # ray/wall intersection, which only cares about the actual shape. Use a
    # lightly simplified copy for the reflection math only; coverage/output
    # stay in full continuous space regardless.
    simplify_tol = max(1.0, (maxx - minx + maxy - miny) * 0.0015)
    wall_polygon = polygon.simplify(simplify_tol, preserve_topology=True)
    if wall_polygon.is_empty or wall_polygon.geom_type != "Polygon":
        wall_polygon = polygon
    rings = _polygon_rings(wall_polygon)

    grid_res = max(4, int(coverage_grid_resolution))
    cell_size = max(maxx - minx, maxy - miny) / grid_res
    gw = max(1, int(math.ceil((maxx - minx) / cell_size)))
    gh = max(1, int(math.ceil((maxy - miny) / cell_size)))
    grid = np.zeros((gh, gw), dtype=float)
    # Look-ahead distance for coverage scoring: needs to be long enough that
    # the jitter-cone candidates actually diverge into different ground
    # before being compared, otherwise they all score roughly the same and
    # the bias has no effect. A quarter of the shape's longer bounding-box
    # dimension works well in practice.
    lookahead = max(maxx - minx, maxy - miny) * 0.25

    rng = random.Random(seed)
    coverage_bias = min(max(coverage_bias, 0.0), 1.0)

    paths = []
    for _ in range(int(num_balls)):
        start = _random_point_in_polygon(polygon, rng)
        if start is None:
            continue
        angle0 = rng.uniform(0, 2 * math.pi)
        direction = (math.cos(angle0), math.sin(angle0))
        path = _compute_ball_trajectory(
            rings, start, direction, total_path_length, deflection_jitter_deg,
            coverage_bias, grid, minx, miny, cell_size, gw, gh, lookahead, rng
        )
        if max_edge_len:
            path = subdivide_line(path, max_edge_len)
        if len(path) >= 2:
            paths.append(path)

    return paths
