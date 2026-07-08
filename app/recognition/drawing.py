"""
Frame drawing utilities.

Draws a modern AI-style bounding box with corner lines only (NOT a full rectangle).
Also draws the recognition label (name + confidence) above the box.
"""

import cv2
import numpy as np


# Visual constants
_COLOR_KNOWN    = (0, 255, 120)    # Green — recognized student
_COLOR_UNKNOWN  = (0, 120, 255)    # Orange — stranger
_COLOR_SCANNING = (80, 180, 255)   # Blue — detecting, not yet recognized
_CORNER_LEN_RATIO = 0.22           # Corner line length as fraction of box side
_THICKNESS = 2
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_face_box(
    frame: np.ndarray,
    bbox: list | np.ndarray,
    label: str = "",
    confidence: float = 0.0,
    state: str = "scanning",   # "known" | "unknown" | "scanning"
) -> np.ndarray:
    """
    Draw corner-line bounding box and label on frame.

    Args:
        frame:      BGR image (modified in-place, also returned)
        bbox:       [x1, y1, x2, y2] in pixel coords
        label:      Student name or "Stranger"
        confidence: Recognition confidence 0.0–1.0
        state:      Controls color scheme

    Returns:
        Modified frame
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]

    color = {
        "known":    _COLOR_KNOWN,
        "unknown":  _COLOR_UNKNOWN,
        "scanning": _COLOR_SCANNING,
    }.get(state, _COLOR_SCANNING)

    w = x2 - x1
    h = y2 - y1
    cx = int(w * _CORNER_LEN_RATIO)
    cy = int(h * _CORNER_LEN_RATIO)

    # Top-left corner
    cv2.line(frame, (x1, y1), (x1 + cx, y1), color, _THICKNESS)
    cv2.line(frame, (x1, y1), (x1, y1 + cy), color, _THICKNESS)

    # Top-right corner
    cv2.line(frame, (x2, y1), (x2 - cx, y1), color, _THICKNESS)
    cv2.line(frame, (x2, y1), (x2, y1 + cy), color, _THICKNESS)

    # Bottom-left corner
    cv2.line(frame, (x1, y2), (x1 + cx, y2), color, _THICKNESS)
    cv2.line(frame, (x1, y2), (x1, y2 - cy), color, _THICKNESS)

    # Bottom-right corner
    cv2.line(frame, (x2, y2), (x2 - cx, y2), color, _THICKNESS)
    cv2.line(frame, (x2, y2), (x2, y2 - cy), color, _THICKNESS)

    # Small dot at each corner tip (optional — adds polish)
    for pt in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
        cv2.circle(frame, pt, 3, color, -1)

    # Label above the box
    if label:
        if confidence > 0:
            display_text = f"{label}  {confidence * 100:.0f}%"
        else:
            display_text = label

        font_scale = 0.55
        thickness = 1
        (tw, th), baseline = cv2.getTextSize(display_text, _FONT, font_scale, thickness)

        # Background pill for readability
        pad = 5
        lx = x1
        ly = y1 - th - pad * 2 - baseline
        if ly < 0:
            ly = y2 + pad

        cv2.rectangle(
            frame,
            (lx, ly),
            (lx + tw + pad * 2, ly + th + pad * 2 + baseline),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            frame,
            display_text,
            (lx + pad, ly + th + pad),
            _FONT,
            font_scale,
            (0, 0, 0),   # Black text on colored background
            thickness,
            cv2.LINE_AA,
        )

    return frame


def draw_fps(frame: np.ndarray, fps: float) -> np.ndarray:
    """Draw FPS counter in top-right corner."""
    text = f"FPS: {fps:.1f}"
    (tw, _), _ = cv2.getTextSize(text, _FONT, 0.5, 1)
    x = frame.shape[1] - tw - 10
    cv2.putText(frame, text, (x, 22), _FONT, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
    return frame
