# processor.py
# Phase 3: adds Canny edge detection and contrast enhancement.

import cv2
import numpy as np
from config import ASCII_WIDTH, ASCII_HEIGHT, COLORMAP, CANNY_LOW, CANNY_HIGH


def to_grayscale(frame):
    """BGR → grayscale. Output: (H, W) uint8."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def resize_for_ascii(gray_frame):
    """Downsample to the ASCII grid size. INTER_AREA = best quality when shrinking."""
    return cv2.resize(
        gray_frame,
        (ASCII_WIDTH, ASCII_HEIGHT),
        interpolation=cv2.INTER_AREA
    )


def enhance_contrast(gray_resized):
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization).

    Standard histogram equalization stretches contrast globally —
    a very bright patch washes out everything else.
    CLAHE divides the image into small tiles and equalizes each
    locally, then blends the results. This makes dim regions
    (e.g. your face in shadow) much more visible in the ASCII output
    without blowing out bright regions.

    clipLimit: max contrast amplification per tile.
               Higher = more contrast, more noise. 2.0 is a safe default.
    tileGridSize: tile size in pixels. (4,4) is fine at our small resolution.
    """
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    return clahe.apply(gray_resized)


def thermal_colormap(gray_resized):
    """Apply the chosen colormap. Returns (H, W, 3) BGR."""
    return cv2.applyColorMap(gray_resized, COLORMAP)


def detect_edges(gray_resized):
    """
    Canny edge detection on the small ASCII grid.

    Returns a binary mask (H, W) uint8:
        255 = edge pixel
        0   = non-edge pixel

    Why blur first?
        Canny needs clean gradients. A single noisy pixel can create
        a spurious gradient. The 3×3 Gaussian blur smooths noise without
        destroying real edges. This is the standard pre-processing step.

    Why detect on the small grid?
        Running Canny on the full 640×480 frame and resizing the result
        introduces aliasing in the edge mask. Running it on the already-
        resized grayscale is faster AND produces edges that align exactly
        with the ASCII character grid.
    """
    # Gentle blur to suppress pixel-level noise before edge detection.
    # (3, 3) kernel at sigma=0 — OpenCV auto-computes sigma from kernel size.
    blurred = cv2.GaussianBlur(gray_resized, (3, 3), 0)

    # Canny: returns a binary uint8 mask (255 = edge, 0 = background).
    edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)
    return edges


def process_frame(frame):
    """
    Full pipeline for all render modes.

    Returns:
        gray_resized   (H, W)    — grayscale pixel grid, contrast-enhanced
        color_resized  (H, W, 3) — thermal colormap applied
        edge_mask      (H, W)    — binary Canny edge mask
    """
    gray         = to_grayscale(frame)
    resized      = resize_for_ascii(gray)
    enhanced     = enhance_contrast(resized)
    color        = thermal_colormap(enhanced)
    edges        = detect_edges(enhanced)
    return enhanced, color, edges
