"""
AM spiral fill.

Same idea as the regular amplitude-modulated (AM) fill, but instead of
superimposing the sine-wave carrier onto straight parallel scan lines, it's
superimposed onto a single continuous outward Archimedean spiral covering
the canvas. The carrier's phase runs along the spiral's own arc length (so
it keeps a consistent visual frequency however tightly the spiral winds),
its amplitude is scaled by the same "brightness envelope" idea as the
straight-line version (sampled from the source image at each point), and
the modulated offset is applied perpendicular to the spiral's local
direction of travel at that point.

There's no scan-angle control here - a spiral doesn't have one - the
spiral's own pitch (radial gap between consecutive windings) takes the
place of the parallel-fill's line spacing.
"""

import math

import numpy as np
import cv2


def _to_gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img


def _sample_brightness(img_gray, xs, ys):
    """Bilinear-sample (inverted, 0-1 normalized) brightness at arbitrary (xs, ys) points."""
    h, w = img_gray.shape
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)

    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)

    x0c = np.clip(x0, 0, w - 1)
    x1c = np.clip(x0 + 1, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)

    dx = np.clip(xs - x0, 0.0, 1.0)
    dy = np.clip(ys - y0, 0.0, 1.0)

    v00 = img_gray[y0c, x0c].astype(float)
    v10 = img_gray[y0c, x1c].astype(float)
    v01 = img_gray[y1c, x0c].astype(float)
    v11 = img_gray[y1c, x1c].astype(float)

    samples = (
        v00 * (1 - dx) * (1 - dy)
        + v10 * dx * (1 - dy)
        + v01 * (1 - dx) * dy
        + v11 * dx * dy
    )

    samples = 255.0 - samples  # invert: dark image areas -> strong signal
    mn, mx = samples.min(), samples.max()
    if mx - mn < 1e-9:
        return np.zeros_like(samples)
    return (samples - mn) / (mx - mn)


def _archimedean_spiral_points(center, pitch, max_radius, sampling_density):
    """
    Sample points along a single outward Archimedean spiral (r = k*theta,
    with k chosen so radius grows by exactly `pitch` per full turn) from
    the center out to max_radius, spaced roughly `1 / sampling_density`
    pixels of arc length apart.
    """
    if pitch <= 0 or max_radius <= 0:
        return [], []

    k = pitch / (2 * math.pi)
    theta_max = max_radius / k
    target_ds = max(1.0 / max(sampling_density, 1e-6), 0.25)

    cx, cy = center
    theta = 0.0
    xs, ys = [], []
    while True:
        r = k * theta
        xs.append(cx + r * math.cos(theta))
        ys.append(cy + r * math.sin(theta))
        if theta >= theta_max:
            break
        ds_dtheta = math.hypot(r, k)  # |d(position)/d(theta)| for this spiral
        theta += target_ds / max(ds_dtheta, 1e-6)

    return xs, ys


def create_am_spiral_polyline(img, center, pitch, max_radius, sampling_density,
                               envelope_smoothing_strength, amplitude, cyc_per_pix):
    """Build one continuous AM-modulated Archimedean spiral covering a circle of `max_radius` around `center`."""
    xs, ys = _archimedean_spiral_points(center, pitch, max_radius, sampling_density)
    n = len(xs)
    if n < 2:
        return []

    img_gray = _to_gray(img)
    envelope = _sample_brightness(img_gray, xs, ys)

    if envelope_smoothing_strength > 1:
        window = min(int(envelope_smoothing_strength), n - 1)
        if window % 2 == 0:
            window -= 1
        if window >= 3:
            kernel = np.ones(window) / window
            envelope = np.convolve(envelope, kernel, mode="same")

    xs = np.array(xs)
    ys = np.array(ys)

    # Phase runs along the spiral's own arc length (not raw x/y), so the
    # carrier keeps a consistent spatial frequency along the whole spiral.
    seg_len = np.hypot(np.diff(xs), np.diff(ys))
    arc_len = np.concatenate([[0.0], np.cumsum(seg_len)])

    carrier = np.sin(2 * np.pi * cyc_per_pix * arc_len)
    am_signal = carrier * envelope
    denom = np.max(np.abs(am_signal)) or 1
    am_signal = am_signal / denom * amplitude

    # Local perpendicular (normal) direction at each sample, from the
    # spiral's own local tangent (central differences).
    tx = np.gradient(xs)
    ty = np.gradient(ys)
    norm = np.hypot(tx, ty)
    norm[norm < 1e-9] = 1.0
    px = -ty / norm
    py = tx / norm

    xs_mod = xs + px * am_signal
    ys_mod = ys + py * am_signal

    return [(float(xs_mod[i]), float(ys_mod[i])) for i in range(n)]


def generate_am_spiral_polyline(img, pitch, sampling_density=0.2,
                                 envelope_smoothing_strength=3, amplitude=5,
                                 cyc_per_pix=0.05):
    """Generate the single AM-modulated spiral polyline covering the whole image canvas, centered on it."""
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)
    # A little margin past the farthest corner so the spiral fully covers it.
    max_radius = math.hypot(w, h) / 2.0 + max(pitch, 1.0)

    return create_am_spiral_polyline(
        img, center, pitch, max_radius, sampling_density,
        envelope_smoothing_strength, amplitude, cyc_per_pix
    )
