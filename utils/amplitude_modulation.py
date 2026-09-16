import numpy as np
import cv2
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union


# ---------------------------------------------------------
# Sample brightness along a spatial line (LOW RES CONTROLLED)
# ---------------------------------------------------------
def sample_line_brightness(img, start, end, sampling_density):
    if len(img.shape) == 3:
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = img.copy()

    x0, y0 = start
    x1, y1 = end

    physical_length = np.hypot(x1 - x0, y1 - y0)
    line_length = max(2, int(physical_length * sampling_density))

    xs = np.linspace(x0, x1, line_length)
    ys = np.linspace(y0, y1, line_length)

    h, w = img_gray.shape
    mask = (xs >= 0) & (xs < w - 1) & (ys >= 0) & (ys < h - 1)

    xs = xs[mask]
    ys = ys[mask]

    if len(xs) < 2:
        return np.array([])

    def sample_bilinear(x, y):
        x0_i, y0_i = int(np.floor(x)), int(np.floor(y))
        x1_i, y1_i = x0_i + 1, y0_i + 1

        dx, dy = x - x0_i, y - y0_i

        v00 = img_gray[y0_i, x0_i]
        v10 = img_gray[y0_i, x1_i]
        v01 = img_gray[y1_i, x0_i]
        v11 = img_gray[y1_i, x1_i]

        return (
            v00 * (1 - dx) * (1 - dy)
            + v10 * dx * (1 - dy)
            + v01 * (1 - dx) * dy
            + v11 * dx * dy
        )

    samples = np.array([sample_bilinear(x, y) for x, y in zip(xs, ys)])

    # Invert brightness
    samples = 255 - samples

    # Normalize 0–1
    mn, mx = samples.min(), samples.max()
    if mx - mn == 0:
        return np.zeros_like(samples)

    return (samples - mn) / (mx - mn)


# ---------------------------------------------------------
# Create AM polyline (LOW RES GEOMETRY)
# ---------------------------------------------------------
def create_am_polyline(
    img,
    start_point,
    end_point,
    sampling_density,
    envelope_smoothing_strength,
    amplitude,
    cyc_per_pix,
):
    envelope = sample_line_brightness(
        img, start_point, end_point, sampling_density
    )

    if len(envelope) < 2:
        return []

    line_length = len(envelope)

    # ---------------------------------------------------------
    # Smooth envelope (optional)
    # ---------------------------------------------------------
    if envelope_smoothing_strength > 1:
        window = min(envelope_smoothing_strength, line_length - 1)
        if window % 2 == 0:
            window -= 1

        kernel = np.ones(window) / window
        envelope = np.convolve(envelope, kernel, mode="same")

    # ---------------------------------------------------------
    # Carrier wave (same LOW resolution)
    # ---------------------------------------------------------
    xs = np.linspace(start_point[0], end_point[0], line_length)
    ys = np.linspace(start_point[1], end_point[1], line_length)

    angle_rad = np.arctan2(
        end_point[1] - start_point[1],
        end_point[0] - start_point[0],
    )

    kx = np.cos(angle_rad) * cyc_per_pix
    ky = np.sin(angle_rad) * cyc_per_pix

    phase = kx * xs + ky * ys
    carrier = np.sin(2 * np.pi * phase)

    # AM modulation
    am_signal = carrier * envelope

    # Normalize amplitude
    denom = np.max(np.abs(am_signal)) or 1
    am_signal = am_signal / denom * amplitude

    # ---------------------------------------------------------
    # Offset perpendicular to line
    # ---------------------------------------------------------
    dx = end_point[0] - start_point[0]
    dy = end_point[1] - start_point[1]
    norm = np.hypot(dx, dy) or 1.0

    px = -dy / norm
    py = dx / norm

    xs_mod = xs + px * am_signal
    ys_mod = ys + py * am_signal

    return [(float(xs_mod[i]), float(ys_mod[i])) for i in range(line_length)]


# ---------------------------------------------------------
# Generate all scanlines
# ---------------------------------------------------------
def generate_all_am_polylines(
    img,
    angle_deg=30,
    am_line_spacing=40,
    sampling_density=0.2,
    envelope_smoothing_strength=3,
    am_amplitude=5,
    cyc_per_pix=0.05,step_size=0.2
):
    h, w = img.shape[:2]
    angle_rad = np.deg2rad(angle_deg)

    dx, dy = np.cos(angle_rad), np.sin(angle_rad)
    px, py = -dy, dx

    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]])
    projections = corners @ np.array([px, py])
    min_proj, max_proj = projections.min(), projections.max()

    num_lines = int(np.ceil((max_proj - min_proj) / am_line_spacing))
    offsets = np.linspace(min_proj, max_proj, num_lines)

    polylines = []

    for offset in offsets:
        line_origin = offset * np.array([px, py])

        intersections = []
        padding = 2

        borders = [
            ((padding, padding), (w, padding)),
            ((w - padding, padding), (w - padding, h - padding)),
            ((w - padding, h - padding), (padding, h - padding)),
            ((padding, h - padding), (padding, padding)),
        ]

        for (bx1, by1), (bx2, by2) in borders:
            denom = dx * (by2 - by1) - dy * (bx2 - bx1)
            if denom == 0:
                continue

            t = (
                (bx1 - line_origin[0]) * (by2 - by1)
                - (by1 - line_origin[1]) * (bx2 - bx1)
            ) / denom

            u = (
                (bx1 - line_origin[0]) * dy
                - (by1 - line_origin[1]) * dx
            ) / denom

            if 0 <= u <= 1:
                ix = line_origin[0] + t * dx
                iy = line_origin[1] + t * dy
                intersections.append((ix, iy))

        if len(intersections) < 2:
            continue

        dists = [np.hypot(ix, iy) for ix, iy in intersections]
        sorted_idx = np.argsort(dists)
        start_point = intersections[sorted_idx[0]]
        end_point = intersections[sorted_idx[-1]]

        polyline = create_am_polyline(
            img,
            start_point,
            end_point,
            step_size,
            envelope_smoothing_strength,
            am_amplitude,
            cyc_per_pix,
        )

        if polyline:
            polylines.append(polyline)

    return polylines


# ---------------------------------------------------------
# Cropping helper (unchanged)
# ---------------------------------------------------------
def crop_lines_with_polygons(lines, polygons):
    poly_union = unary_union(polygons)

    cropped = []

    for line in lines:
        inter = line.intersection(poly_union)

        if inter.is_empty:
            continue

        if isinstance(inter, LineString):
            cropped.append(inter)

        elif isinstance(inter, MultiLineString):
            for geom in inter.geoms:
                cropped.append(geom)

        elif hasattr(inter, "geoms"):
            for geom in inter.geoms:
                if isinstance(geom, LineString):
                    cropped.append(geom)

    return cropped
