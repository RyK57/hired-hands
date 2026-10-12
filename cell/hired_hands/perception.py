"""What the head camera sees: the marker sheet fixes the table frame, and coloured objects on it become
numbered candidates with table coordinates."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .board import DICTIONARY, MARKERS, marker_corners_table
from .table import TableMap, work_area

MIN_MARKERS = 2
MIN_AREA_FRACTION = 0.004    # of the work area, in pixels
MAX_AREA_FRACTION = 0.25

# Colour classes. Saturated objects are told apart by hue; white ones are bright and unsaturated. A wooden
# table is dim and only mildly saturated, so it falls below both rules. Override any value in
# state/perception.json to suit the light on the day.
DEFAULT_THRESHOLDS = {
    "saturation_min": 130, "value_min": 110,        # a coloured object
    "white_saturation_max": 60, "white_value_min": 185,  # a white object
    "close_px": 9,                                   # merge holes in lattice-like objects
    "table_hue_tolerance": 10, "table_saturation_tolerance": 50, "table_value_tolerance": 60,   # what still counts as table
}
SATURATION_MIN = DEFAULT_THRESHOLDS["saturation_min"]
VALUE_MIN = DEFAULT_THRESHOLDS["value_min"]

# hue (OpenCV 0-180) -> name; red wraps around
HUE_NAMES = (
    (0, 8, "red"), (8, 20, "orange"), (20, 34, "yellow"), (34, 82, "green"), (82, 98, "cyan"),
    (98, 128, "blue"), (128, 152, "purple"), (152, 172, "pink"), (172, 181, "red"),
)
PALETTE = (
    (0, 200, 255), (255, 128, 0), (0, 255, 128), (255, 0, 200), (0, 128, 255), (255, 255, 0),
)


class SceneError(RuntimeError):
    pass


def thresholds() -> dict[str, int]:
    import json

    from .config import settings
    path = settings().state_dir / "perception.json"
    out = dict(DEFAULT_THRESHOLDS)
    if path.exists():
        out.update({k: int(v) for k, v in json.loads(path.read_text()).items() if k in out})
    return out


def hue_name(hue: float) -> str:
    if hue < 0:
        return "white"
    for lo, hi, name in HUE_NAMES:
        if lo <= hue < hi:
            return name
    return "red"


@dataclass(frozen=True)
class Candidate:
    index: int
    colour: str
    centre_px: tuple[float, float]
    centre_table: tuple[float, float] | None   # known only once the table has been measured
    area_px: int
    bbox: tuple[int, int, int, int]
    hue: float

    @property
    def label(self) -> str:
        return f"{self.index}: {self.colour}"

    def to_dict(self) -> dict:
        return {
            "index": self.index, "colour": self.colour,
            "px": [round(self.centre_px[0], 1), round(self.centre_px[1], 1)],
            "table": [round(self.centre_table[0], 4), round(self.centre_table[1], 4)] if self.centre_table else None,
            "area_px": self.area_px,
        }


@dataclass
class Scene:
    image: np.ndarray
    homography: np.ndarray | None     # pixels -> table (m); None until the table has been measured
    markers: list[int]
    candidates: list[Candidate] = field(default_factory=list)
    taken_at: float = field(default_factory=time.time)

    @property
    def mapped(self) -> bool:
        return self.homography is not None

    def annotated(self) -> np.ndarray:
        out = self.image.copy()
        if self.homography is not None:
            (ax, ay), (bx, by) = work_area()
            area = np.array([[ax, ay], [bx, ay], [bx, by], [ax, by]], dtype=np.float32)
            poly = table_to_px(self.homography, area).astype(np.int32)
            cv2.polylines(out, [poly], True, (90, 90, 90), 1, cv2.LINE_AA)
        for c in self.candidates:
            colour = PALETTE[c.index % len(PALETTE)]
            x, y = int(c.centre_px[0]), int(c.centre_px[1])
            cv2.circle(out, (x, y), 16, colour, 2, cv2.LINE_AA)
            cv2.putText(out, str(c.index), (x - 7, y + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(out, str(c.index), (x - 7, y + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.65, colour, 2, cv2.LINE_AA)
        return out


    def find(self, index: int) -> Candidate | None:
        return next((c for c in self.candidates if c.index == index), None)


def px_to_table(h: np.ndarray, px: np.ndarray) -> np.ndarray:
    pts = cv2.perspectiveTransform(px.reshape(-1, 1, 2).astype(np.float32), h)
    return pts.reshape(-1, 2)


def table_to_px(h: np.ndarray, table: np.ndarray) -> np.ndarray:
    pts = cv2.perspectiveTransform(table.reshape(-1, 1, 2).astype(np.float32), np.linalg.inv(h))
    return pts.reshape(-1, 2)


def find_table(image: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Homography from image pixels to the table frame: from the sheet's markers when they are in view,
    otherwise from the map the arms measured themselves."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY),
                                       cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(gray)
    src, dst, found = [], [], []
    if ids is not None:
        for quad, marker_id in zip(corners, ids.flatten()):
            marker_id = int(marker_id)
            if marker_id not in MARKERS:
                continue
            src.append(quad.reshape(4, 2))
            dst.append(marker_corners_table(marker_id))
            found.append(marker_id)
    if len(found) >= MIN_MARKERS:
        h, _ = cv2.findHomography(np.concatenate(src), np.concatenate(dst), cv2.RANSAC, 0.004)
        if h is not None:
            return h, sorted(found)
    table = TableMap.load()
    if table is not None:
        return table.homography, []
    raise SceneError("the table is not calibrated and no markers are in view")


def table_mask(hsv: np.ndarray, within: np.ndarray, th: dict[str, int]) -> np.ndarray:
    """Pixels that look like the table itself: the dominant colour of the frame, give or take. A wooden
    table is both coloured and bright enough to pass the object rules, so it is taken out by name."""
    sample = hsv[within > 0]
    if len(sample) == 0:
        return np.zeros(hsv.shape[:2], dtype=np.uint8)
    hue, sat, val = (float(np.median(sample[:, k])) for k in range(3))
    if sat < th["white_saturation_max"] and val >= th["white_value_min"]:
        return np.zeros(hsv.shape[:2], dtype=np.uint8)   # a white table is told apart from white objects by nothing; leave it
    d_hue = np.minimum(np.abs(hsv[..., 0].astype(int) - hue), 180 - np.abs(hsv[..., 0].astype(int) - hue))
    near = (d_hue <= th["table_hue_tolerance"]) & (np.abs(hsv[..., 1].astype(int) - sat) <= th["table_saturation_tolerance"]) \
        & (np.abs(hsv[..., 2].astype(int) - val) <= th["table_value_tolerance"])
    return (near.astype(np.uint8) * 255)


def find_objects(image: np.ndarray, h: np.ndarray | None) -> list[Candidate]:
    """Saturated blobs on the table, numbered left to right then front to back. With a table map only the
    work area counts and positions are in metres; without one the whole frame counts and positions are pixels."""
    mask_area = np.zeros(image.shape[:2], dtype=np.uint8)
    if h is not None:
        (ax, ay), (bx, by) = work_area()
        area = np.array([[ax, ay], [bx, ay], [bx, by], [ax, by]], dtype=np.float32)
        poly = table_to_px(h, area).astype(np.int32)
        cv2.fillPoly(mask_area, [poly], 255)
    else:
        mask_area[:] = 255
    area_px = int(cv2.countNonZero(mask_area))
    if area_px == 0:
        return []

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    th = thresholds()
    not_table = cv2.bitwise_not(table_mask(hsv, mask_area, th))
    classes = {
        "coloured": cv2.inRange(hsv, (0, th["saturation_min"], th["value_min"]), (180, 255, 255)),
        "white": cv2.inRange(hsv, (0, 0, th["white_value_min"]), (180, th["white_saturation_max"], 255)),
    }
    close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (th["close_px"], th["close_px"]))
    open_ = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    found = []
    # each colour class is segmented on its own, so a white object touching an orange one stays separate
    for kind, raw in classes.items():
        mask = cv2.bitwise_and(cv2.bitwise_and(raw, mask_area), not_table)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close)   # merge the gaps of lattice-like objects
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_)    # then drop speckle
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, count):
            area_i = int(stats[i, cv2.CC_STAT_AREA])
            if not (MIN_AREA_FRACTION * area_px <= area_i <= MAX_AREA_FRACTION * area_px):
                continue
            cx, cy = centroids[i]
            pixels = hsv[(labels == i) & (raw > 0)]
            hue = -1.0 if kind == "white" else float(np.median(pixels[:, 0])) if len(pixels) else 0.0
            table = px_to_table(h, np.array([[cx, cy]], dtype=np.float32))[0] if h is not None else None
            bbox = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                    int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            found.append((table, (float(cx), float(cy)), area_i, bbox, hue))

    if h is not None:
        found.sort(key=lambda f: (round(f[0][1], 2), f[0][0]))
    else:
        found.sort(key=lambda f: (-round(f[1][1] / 40), f[1][0]))   # image rows bottom-up, then left to right
    return [
        Candidate(index=n + 1, colour=hue_name(hue), centre_px=px,
                  centre_table=(float(t[0]), float(t[1])) if t is not None else None,
                  area_px=a, bbox=bbox, hue=hue)
        for n, (t, px, a, bbox, hue) in enumerate(found)
    ]


def observe(image: np.ndarray) -> Scene:
    try:
        h, markers = find_table(image)
    except SceneError:
        h, markers = None, []
    return Scene(image=image, homography=h, markers=markers, candidates=find_objects(image, h))
