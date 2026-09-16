"""
Foam / relaxed-Voronoi (Centroidal Voronoi Tessellation) fill.

Pipeline:
    1. Scatter points inside the contour polygon with Poisson-disk sampling
       (evenly spaced, no clustering).
    2. Build the Voronoi diagram of those points.
    3. Clip every Voronoi cell to the contour polygon.
    4. Move each point to the centroid of its own clipped cell, rebuild the
       Voronoi diagram and reclip - repeat a few times (Lloyd's relaxation).
       This turns the raw, angular Voronoi mesh into a Centroidal Voronoi
       Tessellation (CVT), which reads as round, bubble-like "foam" cells
       instead of cracked glass.
    5. Extract the unique cell edges, optionally with a slight outward bulge
       so straight Voronoi edges read as soap-film curves.
    6. Order/duplicate those edges into as few continuous pen-down strokes
       as possible (ideally one per connected patch of cells), retracing an
       edge when needed to reach an unvisited one rather than lifting the
       pen - a standard "route inspection" / Chinese-Postman approach.

Only the standard library, numpy, scipy (Voronoi) and shapely (already a
project dependency) are used.
"""

import heapq

import math
import random

import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from utils.lawnmower_fill import subdivide_line

Point2D = tuple  # (x, y)


# ---------------------------------------------------------------------
# 1. Poisson-disk sampling inside a polygon
# ---------------------------------------------------------------------

def _estimate_spacing(area, num_points, packing=0.85):
    """
    Rough spacing estimate so that Poisson-disk sampling with this radius
    produces on the order of `num_points` samples inside a region of the
    given area. Poisson-disk packing density isn't exact, so this is a
    starting point - actual point count is trimmed afterwards if needed.
    """
    if num_points <= 0 or area <= 0:
        return 0.0
    return math.sqrt((area * packing) / num_points)


def poisson_disk_sample(polygon, spacing_center, edge_density_bias=0.0,
                         k=30, seed=None, max_points=None):
    """
    Bridson-style Poisson-disk sampling restricted to `polygon`, with an
    optional variable radius so points can be packed tighter near the
    contour edge and looser toward the center (or vice-versa).

    edge_density_bias:
        0.0  -> uniform spacing everywhere (spacing_center).
        > 0  -> smaller cells (denser points) near the contour edge and
                bigger cells (sparser points) toward the middle, like real
                foam where bubbles near a wall get squeezed smaller.
    """
    rng = random.Random(seed)
    minx, miny, maxx, maxy = polygon.bounds
    if maxx <= minx or maxy <= miny or spacing_center <= 0:
        return []

    prepared_polygon = prep(polygon)  # much faster repeated .contains() checks
    boundary = polygon.boundary

    spacing_edge = spacing_center / (1.0 + max(0.0, edge_density_bias))
    # Distance (in source units) over which the local spacing fades from
    # the edge value to the center value.
    edge_falloff = max(maxx - minx, maxy - miny) * 0.25

    def local_radius(x, y):
        if edge_density_bias <= 0:
            return spacing_center
        d = boundary.distance(Point(x, y))
        t = min(d / edge_falloff, 1.0) if edge_falloff > 0 else 1.0
        return spacing_edge + (spacing_center - spacing_edge) * t

    # Grid sized to the smallest possible spacing so neighbor lookups stay cheap.
    min_possible_r = min(spacing_center, spacing_edge)
    cell_size = min_possible_r / math.sqrt(2)
    grid_w = int(math.ceil((maxx - minx) / cell_size)) + 1
    grid_h = int(math.ceil((maxy - miny) / cell_size)) + 1
    grid = {}
    samples = []
    radii = []  # local_radius for each sample, computed once and cached
    active = []

    def grid_coords(pt):
        gx = int((pt[0] - minx) / cell_size)
        gy = int((pt[1] - miny) / cell_size)
        return gx, gy

    def fits(pt, pt_r):
        gx, gy = grid_coords(pt)
        span = int(math.ceil(spacing_center / cell_size)) + 1
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

    # Seed point.
    for _ in range(1000):
        x0 = rng.uniform(minx, maxx)
        y0 = rng.uniform(miny, maxy)
        if prepared_polygon.contains(Point(x0, y0)):
            samples.append((x0, y0))
            radii.append(local_radius(x0, y0))
            grid[grid_coords((x0, y0))] = 0
            active.append(0)
            break
    else:
        return []  # contour too thin/small to seed a point

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
            if not prepared_polygon.contains(Point(nx, ny)):
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

    return samples


# ---------------------------------------------------------------------
# 2-4. Bounded Voronoi diagram, contour clipping, Lloyd's relaxation
# ---------------------------------------------------------------------

def _bounded_voronoi_cells(points, polygon):
    """
    Build the Voronoi diagram of `points` and return, for each point, its
    cell clipped to `polygon` (or None if degenerate/empty).

    Plain scipy Voronoi regions for points near the outside of the point
    set are unbounded (open) polygons. To close them we mirror every point
    across the four edges of the polygon's bounding box before building the
    diagram; the mirrored points are only used to bound the real cells and
    are discarded afterwards. This is a standard trick for turning an
    unbounded Voronoi diagram into a bounded one.
    """
    pts = np.asarray(points, dtype=float)
    minx, miny, maxx, maxy = polygon.bounds

    left = np.column_stack([2 * minx - pts[:, 0], pts[:, 1]])
    right = np.column_stack([2 * maxx - pts[:, 0], pts[:, 1]])
    bottom = np.column_stack([pts[:, 0], 2 * miny - pts[:, 1]])
    top = np.column_stack([pts[:, 0], 2 * maxy - pts[:, 1]])
    all_pts = np.vstack([pts, left, right, bottom, top])

    vor = Voronoi(all_pts)

    cells = []
    for i in range(len(pts)):
        region = vor.regions[vor.point_region[i]]
        if not region or -1 in region:
            cells.append(None)
            continue
        verts = [tuple(vor.vertices[v]) for v in region]
        if len(verts) < 3:
            cells.append(None)
            continue
        try:
            cell_poly = Polygon(verts)
            if not cell_poly.is_valid:
                cell_poly = cell_poly.buffer(0)
            clipped = cell_poly.intersection(polygon)
        except Exception:
            clipped = None
        cells.append(clipped if clipped is not None and not clipped.is_empty else None)

    return cells


def _lloyd_relax(points, polygon, iterations):
    """Repeatedly move each point to its clipped cell's centroid."""
    pts = list(points)
    cells = _bounded_voronoi_cells(pts, polygon)
    for _ in range(max(0, iterations)):
        new_pts = []
        for p, cell in zip(pts, cells):
            if cell is None or cell.is_empty:
                new_pts.append(p)  # nothing to relax toward, keep as-is
                continue
            c = cell.centroid
            new_pts.append((c.x, c.y) if not c.is_empty else p)
        pts = new_pts
        cells = _bounded_voronoi_cells(pts, polygon)
    return pts, cells


# ---------------------------------------------------------------------
# 5. Edge extraction + optional bubble-like bulge
# ---------------------------------------------------------------------

def _extract_unique_edges(cells, precision=3):
    """Collect every cell-boundary segment once (shared edges de-duplicated)."""
    seen = set()
    edges = []

    def add_ring(coords):
        for a, b in zip(coords[:-1], coords[1:]):
            ka = (round(a[0], precision), round(a[1], precision))
            kb = (round(b[0], precision), round(b[1], precision))
            if ka == kb:
                continue
            key = (ka, kb) if ka <= kb else (kb, ka)
            if key in seen:
                continue
            seen.add(key)
            edges.append((a, b))

    for cell in cells:
        if cell is None or cell.is_empty:
            continue
        if cell.geom_type == "Polygon":
            polys = [cell]
        elif cell.geom_type == "MultiPolygon":
            polys = list(cell.geoms)
        else:
            continue
        for poly in polys:
            add_ring(list(poly.exterior.coords))
            for interior in poly.interiors:
                add_ring(list(interior.coords))

    return edges


def _bulge_edge(p1, p2, curvature, samples=6):
    """
    Replace the straight segment p1->p2 with a shallow quadratic-bezier arc
    bulging outward by `curvature` (a fraction of the edge length). The
    bulge direction is picked deterministically from the edge's own
    coordinates so re-running with the same geometry always curves the
    same way.
    """
    if curvature <= 0:
        return [p1, p2]

    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return [p1, p2]

    nx, ny = -dy / length, dx / length  # unit normal
    key = (round(p1[0], 3), round(p1[1], 3), round(p2[0], 3), round(p2[1], 3))
    sign = 1.0 if (hash(key) % 2 == 0) else -1.0
    bulge = curvature * length * sign

    mx = (p1[0] + p2[0]) / 2 + nx * bulge
    my = (p1[1] + p2[1]) / 2 + ny * bulge

    # Quadratic bezier control point chosen so the curve passes exactly
    # through (mx, my) at t = 0.5.
    cx = 2 * mx - 0.5 * p1[0] - 0.5 * p2[0]
    cy = 2 * my - 0.5 * p1[1] - 0.5 * p2[1]

    pts = []
    for i in range(samples + 1):
        t = i / samples
        bx = (1 - t) ** 2 * p1[0] + 2 * (1 - t) * t * cx + t ** 2 * p2[0]
        by = (1 - t) ** 2 * p1[1] + 2 * (1 - t) * t * cy + t ** 2 * p2[1]
        pts.append((bx, by))
    return pts


# ---------------------------------------------------------------------
# 6. Order edges into minimal-pen-lift strokes (route inspection / CPP)
# ---------------------------------------------------------------------
#
# The cell edges form a graph (corners = nodes, edges = cell walls). A
# single pen-down stroke can only trace every edge without lifting if
# every node has an even number of edges meeting at it (an Eulerian
# circuit). Real clipped Voronoi meshes usually have plenty of odd-degree
# nodes (e.g. wherever a cell edge is cut off by the contour boundary), so
# instead we duplicate a shortest path between each pair of odd-degree
# nodes - which is exactly "retrace the shortest bit of existing edge to
# reach an unvisited edge" - to make every node even, then walk the
# resulting Eulerian circuit. This is the standard heuristic solution to
# the route inspection ("Chinese Postman") problem.

def _build_edge_graph(edge_polylines, precision=3):
    """
    edge_polylines: list of point-lists, each a sampled polyline for one
    unique cell edge (its first/last points are the graph nodes; interior
    points, if any, come from edge curvature).

    Returns (adj, edge_info, node_coords):
        adj: dict node_key -> list of (neighbor_key, weight, edge_id)
        edge_info: list of {"a", "b", "points", "length"} indexed by edge_id
        node_coords: dict node_key -> actual (x, y) coordinate
    """
    def key(pt):
        return (round(pt[0], precision), round(pt[1], precision))

    adj = {}
    edge_info = []
    node_coords = {}

    for pts in edge_polylines:
        a, b = key(pts[0]), key(pts[-1])
        if a == b:
            continue  # degenerate edge, nothing to draw
        node_coords.setdefault(a, pts[0])
        node_coords.setdefault(b, pts[-1])
        length = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                     for i in range(len(pts) - 1))
        eid = len(edge_info)
        edge_info.append({"a": a, "b": b, "points": pts, "length": length})
        adj.setdefault(a, []).append((b, length, eid))
        adj.setdefault(b, []).append((a, length, eid))

    return adj, edge_info, node_coords


def _connected_components(adj):
    seen = set()
    comps = []
    for start in adj:
        if start in seen:
            continue
        seen.add(start)
        stack = [start]
        comp = {start}
        while stack:
            u = stack.pop()
            for v, _, _ in adj.get(u, []):
                if v not in seen:
                    seen.add(v)
                    comp.add(v)
                    stack.append(v)
        comps.append(comp)
    return comps


def _dijkstra(adj, source):
    """Shortest distances/predecessor edges from `source` within `adj`."""
    dist = {source: 0.0}
    prev_edge = {}
    visited = set()
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for v, w, eid in adj.get(u, []):
            nd = d + w
            if v not in dist or nd < dist[v] - 1e-12:
                dist[v] = nd
                prev_edge[v] = (u, eid)
                heapq.heappush(heap, (nd, v))
    return dist, prev_edge


def _shortest_path_edge_ids(prev_edge, source, target):
    path = []
    node = target
    while node != source:
        if node not in prev_edge:
            return None  # unreachable - shouldn't happen inside one component
        pnode, eid = prev_edge[node]
        path.append(eid)
        node = pnode
    return path


def _order_edges_for_plotting(edge_polylines, precision=3):
    """
    Turn a bag of unique cell-edge polylines into as few continuous
    pen-down strokes as possible. Returns a list of polylines (strokes) -
    normally just one per connected patch of cells, retracing edges here
    and there when a stroke has to backtrack to reach an unvisited edge.
    """
    if not edge_polylines:
        return []

    adj, edge_info, node_coords = _build_edge_graph(edge_polylines, precision)
    if not adj:
        return []

    strokes = []

    for comp in _connected_components(adj):
        comp_adj = {u: [(v, w, eid) for (v, w, eid) in adj[u] if v in comp] for u in comp}
        degree = {u: len(comp_adj[u]) for u in comp}
        odd_nodes = [u for u in comp if degree[u] % 2 == 1]

        # How many times each edge should be walked: 1 normally, 2+ if it
        # falls on a path used to bridge a pair of odd nodes. Voronoi
        # vertices are generically 3-valent, so most nodes here are odd.
        #
        # Phase 1: pair each odd node with a directly-adjacent odd node
        # (an O(1) adjacency-list check, no shortest-path search at all).
        # Matches are overwhelmingly local in a Voronoi mesh, so this alone
        # resolves the large majority of nodes almost for free.
        # Phase 2: whatever's left (should be a small minority) gets paired
        # with a real shortest-path search - this is the expensive part, so
        # only running it on the leftovers is what keeps things fast at
        # high point counts.
        multiplicity = {}
        if odd_nodes:
            odd_set = set(odd_nodes)
            path_edge_count = {}
            matched = set()

            for u in odd_nodes:
                if u in matched:
                    continue
                best = None
                for v, w, eid in comp_adj[u]:
                    if v != u and v in odd_set and v not in matched:
                        if best is None or w < best[1]:
                            best = (v, w, eid)
                if best is not None:
                    v, w, eid = best
                    matched.add(u)
                    matched.add(v)
                    path_edge_count[eid] = path_edge_count.get(eid, 0) + 1

            leftover = [u for u in odd_nodes if u not in matched]
            if leftover:
                dist_from = {}
                prev_from = {}
                for u in leftover:
                    d, p = _dijkstra(comp_adj, u)
                    dist_from[u] = d
                    prev_from[u] = p

                candidates = sorted(
                    (dist_from[u][v], u, v)
                    for i, u in enumerate(leftover)
                    for v in leftover[i + 1:]
                    if v in dist_from[u]
                )
                for d, u, v in candidates:
                    if u in matched or v in matched:
                        continue
                    matched.add(u)
                    matched.add(v)
                    for eid in _shortest_path_edge_ids(prev_from[u], u, v) or []:
                        path_edge_count[eid] = path_edge_count.get(eid, 0) + 1

            # Where two paths overlap on the same edge, that overlap should
            # cancel (walking it there-and-back-and-there-again is
            # pointless) - only the *parity* of the count matters for
            # fixing node degrees, so an even count needs no duplicate at
            # all and only an odd count needs exactly one.
            multiplicity = {eid: 2 for eid, c in path_edge_count.items() if c % 2 == 1}

        # Build the walk-multigraph: give each required traversal of an edge
        # (multiplicity 1 normally, 2 if it's being retraced) its own
        # independent adjacency-list entry. This matters: Hierholzer's
        # algorithm assumes every adjacency-list entry is a distinct,
        # single-use edge - representing a retraced edge as one entry with
        # a shared "2 uses left" counter breaks that assumption (the
        # traversal pointer never revisits an index, so the second use can
        # silently end up mis-paired with the wrong neighbor). Genuinely
        # duplicating the entry avoids that.
        walk_adj = {u: [] for u in comp}
        uses_left = {}
        instance_source = {}
        next_instance_id = 0
        for eid, info in enumerate(edge_info):
            a, b = info["a"], info["b"]
            if a not in comp:
                continue
            for _ in range(multiplicity.get(eid, 1)):
                iid = next_instance_id
                next_instance_id += 1
                uses_left[iid] = 1
                instance_source[iid] = eid
                walk_adj[a].append((b, iid))
                walk_adj[b].append((a, iid))

        # Hierholzer's algorithm (iterative) - produces an Eulerian circuit
        # of the walk-multigraph, i.e. one continuous stroke for this
        # connected patch of cells.
        start_node = odd_nodes[0] if odd_nodes else next(iter(comp))
        ptr = {u: 0 for u in comp}
        stack = [(start_node, None)]
        circuit = []

        while stack:
            u, in_iid = stack[-1]
            adj_list = walk_adj[u]
            advanced = False
            while ptr[u] < len(adj_list):
                v, iid = adj_list[ptr[u]]
                ptr[u] += 1
                if uses_left.get(iid, 0) > 0:
                    uses_left[iid] -= 1
                    stack.append((v, iid))
                    advanced = True
                    break
            if not advanced:
                circuit.append(stack.pop())

        circuit.reverse()

        # Reconstruct the actual coordinate polyline for this stroke.
        stroke = [node_coords[circuit[0][0]]]
        prev_node = circuit[0][0]
        for node, iid in circuit[1:]:
            info = edge_info[instance_source[iid]]
            pts = info["points"] if info["a"] == prev_node else list(reversed(info["points"]))
            stroke.extend(pts[1:])
            prev_node = node

        if len(stroke) >= 2:
            strokes.append(stroke)

    return strokes


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def generate_foam_voronoi_fill(polygon, num_points=150, relaxation_iterations=5,
                                edge_density_bias=0.0, edge_curvature=0.0,
                                seed=None, max_edge_len=None):
    """
    Generate a relaxed-Voronoi ("foam") fill for a single Polygon.

    Returns a list of polylines - drawing strokes ordered to minimize pen
    lifts (retracing edges where needed) - ready to hand to
    write_linepath_to_gcode/plotting.
    """
    if polygon is None or polygon.is_empty or num_points <= 0:
        return []

    area = polygon.area
    if area <= 0:
        return []

    spacing = _estimate_spacing(area, num_points)
    if spacing <= 0:
        return []

    points = poisson_disk_sample(polygon, spacing, edge_density_bias=edge_density_bias, seed=seed)
    if len(points) < 2:
        return []

    # Poisson-disk sampling only approximates the requested count - trim
    # overshoot so the result stays close to what was asked for.
    if len(points) > num_points:
        rng = random.Random(seed)
        points = rng.sample(points, num_points)

    _, final_cells = _lloyd_relax(points, polygon, int(relaxation_iterations))

    edges = _extract_unique_edges(final_cells)
    if not edges:
        return []

    edge_polylines = [
        _bulge_edge(p1, p2, edge_curvature) if edge_curvature > 0 else [p1, p2]
        for p1, p2 in edges
    ]

    strokes = _order_edges_for_plotting(edge_polylines)

    if max_edge_len:
        strokes = [subdivide_line(s, max_edge_len) for s in strokes]

    return strokes

