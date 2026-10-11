"""The work surface: a printed sheet of four markers that fixes the table frame for the camera.

The table frame has its origin at the centre of the sheet, x to the right and y away from the viewer when the
sheet is read the right way up, in metres. Objects are placed inside the rectangle the markers outline.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

DICTIONARY = cv2.aruco.DICT_4X4_50
MARKER_SIZE_M = 0.040
# marker id -> centre in the table frame (m); a 220 x 140 mm rectangle fits a landscape Letter or A4 sheet
MARKERS: dict[int, tuple[float, float]] = {
    0: (-0.110, 0.070),
    1: (0.110, 0.070),
    2: (0.110, -0.070),
    3: (-0.110, -0.070),
}
WORK_AREA = ((-0.085, -0.045), (0.085, 0.045))  # (min xy, max xy) inside the markers, where objects go

SHEET_W_M, SHEET_H_M = 0.2794, 0.2159  # Letter, landscape
DPI = 300


def _px(metres: float) -> int:
    return int(round(metres / 0.0254 * DPI))


def marker_corners_table(marker_id: int) -> np.ndarray:
    """The four corners of a marker in the table frame, in the order the detector reports them."""
    cx, cy = MARKERS[marker_id]
    h = MARKER_SIZE_M / 2
    return np.array([[cx - h, cy + h], [cx + h, cy + h], [cx + h, cy - h], [cx - h, cy - h]], dtype=np.float32)


def render_sheet(path: Path) -> Path:
    """Write the printable sheet (print at 100 %, landscape)."""
    w, h = _px(SHEET_W_M), _px(SHEET_H_M)
    sheet = np.full((h, w), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    size_px = _px(MARKER_SIZE_M)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return w // 2 + _px(x), h // 2 - _px(y)

    for marker_id, (cx, cy) in MARKERS.items():
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, size_px)
        px, py = to_px(cx, cy)
        x0, y0 = px - size_px // 2, py - size_px // 2
        sheet[y0:y0 + size_px, x0:x0 + size_px] = marker

    (ax, ay), (bx, by) = WORK_AREA
    cv2.rectangle(sheet, to_px(ax, by), to_px(bx, ay), 160, 2)
    bar_y = h - _px(0.012)
    cv2.line(sheet, (w // 2 - _px(0.05), bar_y), (w // 2 + _px(0.05), bar_y), 0, 3)
    cv2.putText(sheet, "100 mm", (w // 2 - _px(0.012), bar_y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
    cv2.putText(sheet, "Hired Hands  work surface", (_px(0.012), _px(0.012)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet)
    return path
