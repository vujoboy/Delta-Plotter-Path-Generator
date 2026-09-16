import cv2
import numpy as np
from skimage.morphology import skeletonize


def extract_centerline_polylines(img, threshold=127, min_length=10):
    """
    Returns: List of polylines [(x, y), ...]
    Includes:
    - skeleton centerlines (for strokes)
    - contour loops (for holes)
    """

    # --- Ensure grayscale ---
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = img.shape

    # --- Threshold ---
    _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
    binary_bool = binary > 0

    # =========================
    # 1. SKELETON (only foreground)
    # =========================
    skeleton = skeletonize(binary_bool)

    # --- Neighbor helper ---
    def neighbors(y, x):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and skeleton[ny, nx]:
                    yield (ny, nx)

    # --- Find nodes ---
    nodes = set()
    for y in range(h):
        for x in range(w):
            if not skeleton[y, x]:
                continue
            n = sum(1 for _ in neighbors(y, x))
            if n != 2:
                nodes.add((y, x))

    # --- Trace skeleton polylines ---
    visited_edges = set()
    polylines = []

    for node in nodes:
        for n in neighbors(*node):

            if (node, n) in visited_edges:
                continue

            path = [node]
            prev = node
            current = n

            while True:
                path.append(current)

                if current in nodes and current != node:
                    break

                neigh = list(neighbors(*current))
                next_pixels = [p for p in neigh if p != prev]

                if not next_pixels:
                    break

                next_pixel = next_pixels[0]

                visited_edges.add((prev, current))
                visited_edges.add((current, prev))

                prev = current
                current = next_pixel

            if len(path) >= min_length:
                polylines.append([(x, y) for y, x in path])

    # =========================
    # 2. HOLES via contours (clean loops)
    # =========================
    contours, hierarchy = cv2.findContours(
    binary,
    cv2.RETR_CCOMP,
    cv2.CHAIN_APPROX_NONE
    )

    if hierarchy is not None:
        hierarchy = hierarchy[0]

        for i, cnt in enumerate(contours):
            parent = hierarchy[i][3]

            # Only holes
            if parent == -1:
                continue

            # --- Reject contours touching image border ---
            touches_border = False
            for p in cnt:
                x, y = p[0]
                if x == 0 or y == 0 or x == w-1 or y == h-1:
                    touches_border = True
                    break

            if touches_border:
                continue

            # Convert to polyline
            pts = [(int(p[0][0]), int(p[0][1])) for p in cnt]

            if len(pts) >= min_length:
                polylines.append(pts)

    return polylines