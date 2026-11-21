"""
Billiard-path contour fill.

Computes the *exact* bounce trajectory of several "balls" inside a contour
using real ray/edge intersection and reflection off the true edge normal
(not sub-stepped, not approximated by nearest vertex). Because it's exact,
each ball's entire path for a given total travel distance can be computed
in one shot -- no per-frame loop, no waitKey, no animation.

This reproduces the long-straight-segment "criss-crossing billiard lines"
look, just computed directly instead of simulated.
"""

import cv2
import numpy as np
import random
import math

# --- Configuration ---
IMAGE_PATH = 'image2.png'
OUTPUT_PATH = 'billiard_fill_result.png'

NUM_BALLS = 1
GRID_ROWS = 3
GRID_COLS = 3

TOTAL_PATH_LENGTH = 200000      # total travel distance per ball, in pixels
DEFLECTION_VARIANCE = 15      # degrees of random jitter added at each bounce
LINE_THICKNESS = 1
CONTOUR_COLOR = (255, 255, 0)  # cyan, BGR
EPS = 1e-6


def find_target_contour(img):
    h_img, w_img = img.shape[:2]
    total_area = w_img * h_img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    if not contours:
        return None

    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) > total_area * 0.98:
            continue
        return c
    return None


def ray_polygon_hit(origin, direction, poly):
    """
    Find the nearest intersection of a ray (origin + t*direction, t>0) with
    the polygon's edges. Returns (t, unit_normal_facing_the_ray) or None.
    poly: Nx2 array of vertices, treated as a closed loop.
    """
    ox, oy = origin
    dx, dy = direction
    best_t = None
    best_normal = None
    n = len(poly)

    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        ex, ey = p2[0] - p1[0], p2[1] - p1[1]

        denom = dx * ey - dy * ex
        if abs(denom) < EPS:
            continue  # parallel

        # Solve origin + t*dir = p1 + u*edge
        qx, qy = p1[0] - ox, p1[1] - oy
        t = (qx * ey - qy * ex) / denom
        u = (qx * dy - qy * dx) / denom

        if t > EPS and 0.0 <= u <= 1.0:
            if best_t is None or t < best_t:
                best_t = t
                # edge normal candidates (perpendicular to edge), pick the
                # one pointing back against the incoming ray direction
                nx, ny = -ey, ex
                length = math.hypot(nx, ny)
                if length < EPS:
                    continue
                nx, ny = nx / length, ny / length
                if nx * dx + ny * dy > 0:
                    nx, ny = -nx, -ny
                best_normal = (nx, ny)

    if best_t is None:
        return None
    return best_t, best_normal


def compute_trajectory(start, direction, poly, total_length, jitter_deg):
    """Returns a list of (x, y) points forming the full bounced path."""
    path = [start]
    pos = start
    d = direction
    remaining = total_length

    while remaining > 0:
        hit = ray_polygon_hit(pos, d, poly)
        if hit is None:
            break  # shouldn't normally happen inside a closed contour

        t, normal = hit
        travel = min(t, remaining)
        new_pos = (pos[0] + d[0] * travel, pos[1] + d[1] * travel)
        path.append(new_pos)
        remaining -= travel

        if travel < t:
            break  # ran out of path length before reaching the wall

        # Reflect: r = d - 2*(d.n)*n
        dot = d[0] * normal[0] + d[1] * normal[1]
        rx = d[0] - 2 * dot * normal[0]
        ry = d[1] - 2 * dot * normal[1]

        # Random deflection jitter
        angle = math.atan2(ry, rx) + math.radians(random.uniform(-jitter_deg, jitter_deg))
        d = (math.cos(angle), math.sin(angle))

        # Nudge slightly inward off the wall to avoid re-hitting the same edge
        pos = (new_pos[0] + normal[0] * 1.0, new_pos[1] + normal[1] * 1.0)
        path[-1] = pos

    return path


def main():
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"Error: Could not load image from '{IMAGE_PATH}'.")
        return

    target_contour = find_target_contour(img)
    if target_contour is None:
        print("Error: No usable contour found.")
        return

    poly = target_contour.reshape(-1, 2).astype(float)
    x, y, w, h = cv2.boundingRect(target_contour)

    # Generate start points on a grid, keep the ones inside the contour
    x_coords = np.linspace(x + 15, x + w - 15, GRID_COLS)
    y_coords = np.linspace(y + 15, y + h - 15, GRID_ROWS)
    starts = []
    for gx in x_coords:
        for gy in y_coords:
            if cv2.pointPolygonTest(target_contour, (float(gx), float(gy)), False) > 0:
                starts.append((float(gx), float(gy)))

    if not starts:
        print("Error: No grid points landed inside the contour.")
        return

    random.shuffle(starts)
    starts = starts[:NUM_BALLS] if len(starts) >= NUM_BALLS else starts

    output = img.copy()

    for start in starts:
        angle = random.uniform(0, 2 * math.pi)
        direction = (math.cos(angle), math.sin(angle))
        path = compute_trajectory(start, direction, poly, TOTAL_PATH_LENGTH, DEFLECTION_VARIANCE)

        color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
        pts = [(int(px), int(py)) for px, py in path]
        for p1, p2 in zip(pts, pts[1:]):
            cv2.line(output, p1, p2, color, LINE_THICKNESS, cv2.LINE_AA)

    cv2.drawContours(output, [target_contour], -1, CONTOUR_COLOR, 3)
    cv2.imwrite(OUTPUT_PATH, output)
    print(f"Placed {len(starts)} bounced paths. Saved to '{OUTPUT_PATH}'.")


if __name__ == "__main__":
    main()