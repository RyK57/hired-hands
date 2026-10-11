"""Forward and inverse kinematics for one arm, and the rigid transform that places it on the shared table.

The gripper frame's z axis is its approach axis: with the arm stretched out it points away from the base, and
with the wrist flexed down it points at the table. A top-down grasp is therefore z = world down, with the
frame's x axis turned to face the base so the jaws straddle the object across the reach direction.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lerobot.model.kinematics import RobotKinematics

from .config import settings
from .rig import ARM_JOINTS, JOINTS

TIP_FRAME = "gripper_frame_link"
MAX_REACH = 0.28   # horizontal distance (m) a vertical grasp can still reach
SEED_POSES = ((-45.0, 45.0, 60.0), (0.0, 40.0, 45.0), (20.0, 20.0, 50.0), (40.0, 0.0, 50.0), (-20.0, 70.0, 40.0))


@contextlib.contextmanager
def _quiet():
    """The model loader reports self-collisions of the neutral pose on stdout; they are not ours."""
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield


def top_down_rotation(azimuth: float) -> np.ndarray:
    """Gripper rotation for a vertical grasp over a point at this azimuth (rad) from the base."""
    c, s = math.cos(azimuth), math.sin(azimuth)
    x_axis = np.array([-c, -s, 0.0])
    z_axis = np.array([0.0, 0.0, -1.0])
    y_axis = np.cross(z_axis, x_axis)
    return np.column_stack([x_axis, y_axis, z_axis])


@dataclass(frozen=True)
class TableFrame:
    """Where an arm's base sits on the table: a 2D rigid transform plus the table height in the arm frame."""
    origin: tuple[float, float]   # the arm base in table coordinates (m)
    yaw: float                    # rotation from arm x to table x (rad)
    z_table: float                # table surface height in the arm frame (m)

    def to_table(self, p_arm) -> np.ndarray:
        x, y = float(p_arm[0]), float(p_arm[1])
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return np.array([c * x - s * y + self.origin[0], s * x + c * y + self.origin[1]])

    def to_arm(self, p_table) -> np.ndarray:
        x, y = float(p_table[0]) - self.origin[0], float(p_table[1]) - self.origin[1]
        c, s = math.cos(-self.yaw), math.sin(-self.yaw)
        return np.array([c * x - s * y, s * x + c * y])

    @classmethod
    def load(cls, role: str) -> "TableFrame | None":
        path = settings().state_dir / "frames" / f"{role}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        return cls(origin=(float(d["origin"][0]), float(d["origin"][1])), yaw=float(d["yaw"]),
                   z_table=float(d["z_table"]))

    def save(self, role: str) -> Path:
        path = settings().state_dir / "frames" / f"{role}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"origin": list(self.origin), "yaw": self.yaw, "z_table": self.z_table},
                                   indent=2) + "\n")
        return path

    @classmethod
    def fit(cls, arm_points: list, table_points: list, z_table: float) -> "TableFrame":
        """Least-squares rigid fit from pairs of the same physical points seen in both frames."""
        a = np.asarray(arm_points, dtype=float)[:, :2]
        b = np.asarray(table_points, dtype=float)[:, :2]
        ca, cb = a.mean(axis=0), b.mean(axis=0)
        h = (a - ca).T @ (b - cb)
        u, _, vt = np.linalg.svd(h)
        d = np.sign(np.linalg.det(vt.T @ u.T))
        r = vt.T @ np.diag([1.0, d]) @ u.T
        yaw = math.atan2(r[1, 0], r[0, 0])
        origin = cb - r @ ca
        return cls(origin=(float(origin[0]), float(origin[1])), yaw=yaw, z_table=z_table)


class Kinematics:
    def __init__(self, urdf: Path | None = None):
        with _quiet():
            self._kin = RobotKinematics(str(urdf or settings().urdf_path), TIP_FRAME, joint_names=list(JOINTS))

    @staticmethod
    def _vector(q: dict[str, float]) -> np.ndarray:
        return np.array([q.get(j, 0.0) for j in JOINTS], dtype=float)

    def pose(self, q: dict[str, float]) -> np.ndarray:
        return self._kin.forward_kinematics(self._vector(q))

    def tip(self, q: dict[str, float]) -> np.ndarray:
        return self.pose(q)[:3, 3]

    def solve(self, q0: dict[str, float], target: np.ndarray, *, iterations: int = 40, tolerance: float = 0.002,
              orientation_weight: float = 0.05) -> tuple[dict[str, float], float]:
        """Joints that put the tip at the 4x4 `target`, starting from `q0`. Returns (joints, position error m)."""
        q = self._vector(q0)
        error = float("inf")
        for _ in range(iterations):
            q = self._kin.inverse_kinematics(q, target, position_weight=1.0, orientation_weight=orientation_weight)
            error = float(np.linalg.norm(self._kin.forward_kinematics(q)[:3, 3] - target[:3, 3]))
            if error < tolerance:
                break
        joints = {j: float(v) for j, v in zip(JOINTS, q)}
        joints["gripper"] = float(q0.get("gripper", 0.0))
        return joints, error

    def solve_top_down(self, q0: dict[str, float], xyz, *, azimuth: float | None = None,
                       **kwargs) -> tuple[dict[str, float], float]:
        """Joints for a vertical grasp with the tip at `xyz` (arm frame), tried from several starting poses."""
        x, y, z = (float(v) for v in xyz)
        target = np.eye(4)
        target[:3, :3] = top_down_rotation(math.atan2(y, x) if azimuth is None else azimuth)
        target[:3, 3] = (x, y, z)
        best: tuple[dict[str, float], float] | None = None
        for seed in self._seeds(q0, math.degrees(math.atan2(y, x))):
            joints, error = self.solve(seed, target, **kwargs)
            if best is None or error < best[1]:
                best = (joints, error)
            if error < kwargs.get("tolerance", 0.002):
                break
        assert best is not None
        return best

    @staticmethod
    def _seeds(q0: dict[str, float], azimuth_deg: float):
        """The present pose first, then a fan of raised poses facing the target."""
        yield q0
        for lift, elbow, wrist in SEED_POSES:
            yield {"shoulder_pan": -azimuth_deg, "shoulder_lift": lift, "elbow_flex": elbow,
                   "wrist_flex": wrist, "wrist_roll": 0.0, "gripper": q0.get("gripper", 0.0)}

    def reach(self, q0: dict[str, float], xyz, tolerance: float = 0.004) -> tuple[bool, float]:
        """Can the arm put its tip at `xyz` top-down, and how far from the base is it."""
        _, error = self.solve_top_down(q0, xyz)
        return error <= tolerance, float(math.hypot(float(xyz[0]), float(xyz[1])))


def within_limits(q: dict[str, float], limits: dict[str, tuple[float, float]] | None = None) -> bool:
    limits = limits or {j: (-110.0, 110.0) for j in ARM_JOINTS}
    return all(lo <= q[j] <= hi for j, (lo, hi) in limits.items() if j in q)
