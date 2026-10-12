"""The table as the cell knows it once it has measured it: where the camera's pixels land, where the arms
stand, and the patch of surface every arm can reach."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .board import WORK_AREA as PRINTED_WORK_AREA
from .config import settings

Area = tuple[tuple[float, float], tuple[float, float]]


def _path() -> Path:
    return settings().state_dir / "frames" / "table.json"


@dataclass(frozen=True)
class TableMap:
    homography: np.ndarray                  # camera pixels -> table metres, from the survey pose
    work_area: Area
    anchor: str                             # the arm whose base frame is the table frame
    bases: dict[str, tuple[float, float, float]]   # role -> (x, y, yaw) of each arm's base on the table
    fit_error_m: float

    def save(self) -> Path:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "homography": self.homography.tolist(),
            "work_area": [list(self.work_area[0]), list(self.work_area[1])],
            "anchor": self.anchor,
            "bases": {k: list(v) for k, v in self.bases.items()},
            "fit_error_m": self.fit_error_m,
        }, indent=2) + "\n")
        return path

    @classmethod
    def load(cls) -> "TableMap | None":
        path = _path()
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        return cls(
            homography=np.asarray(d["homography"], dtype=np.float64),
            work_area=((float(d["work_area"][0][0]), float(d["work_area"][0][1])),
                       (float(d["work_area"][1][0]), float(d["work_area"][1][1]))),
            anchor=d.get("anchor", "left"),
            bases={k: (float(v[0]), float(v[1]), float(v[2])) for k, v in d.get("bases", {}).items()},
            fit_error_m=float(d.get("fit_error_m", 0.0)),
        )

    def layout(self) -> dict:
        """What the dashboard draws."""
        return {
            "anchor": self.anchor,
            "bases": {k: [round(v[0], 4), round(v[1], 4), round(v[2], 4)] for k, v in self.bases.items()},
            "work_area": [[round(self.work_area[0][0], 4), round(self.work_area[0][1], 4)],
                          [round(self.work_area[1][0], 4), round(self.work_area[1][1], 4)]],
        }


def work_area() -> Area:
    """The measured work area when the table has been calibrated, else the printed sheet's."""
    table = TableMap.load()
    return table.work_area if table else PRINTED_WORK_AREA


def reachable_area(bases: dict[str, tuple[float, float, float]], reach_m: float, margin_m: float = 0.03,
                   near_m: float = 0.09) -> Area:
    """The axis-aligned patch inside every working arm's reach and outside its own footprint."""
    lo_x, lo_y, hi_x, hi_y = -1e9, -1e9, 1e9, 1e9
    for x, y, _ in bases.values():
        r = reach_m - margin_m
        lo_x, hi_x = max(lo_x, x - r), min(hi_x, x + r)
        lo_y, hi_y = max(lo_y, y - r), min(hi_y, y + r)
    # keep the patch in front of the arms rather than between their bases
    front = max(y for _, y, _ in bases.values()) + near_m
    lo_y = max(lo_y, front)
    if hi_x - lo_x < 0.06 or hi_y - lo_y < 0.06:
        raise ValueError("the arms do not share enough table to work on; move them closer together")
    return ((lo_x, lo_y), (hi_x, hi_y))
