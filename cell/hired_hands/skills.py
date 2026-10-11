"""What an arm can do on the table: look at it, pick something up, put it down."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .config import settings
from .kinematics import MAX_REACH, Kinematics, TableFrame
from .rig import Arm

Log = Callable[[str], None]

GRIPPER_OPEN = 60.0
GRIPPER_CLOSED = 6.0
HOVER_M = 0.07            # above the table on the way in and out
GRASP_M = 0.012           # jaw centre above the table when closing on a block
DROP_M = 0.045            # release height when placing on or into something
APPROACH_TOLERANCE = 0.004


class SkillError(RuntimeError):
    pass


def _pose_path(name: str) -> Path:
    return settings().state_dir / "poses" / f"{name}.json"


def load_pose(name: str) -> dict[str, float] | None:
    path = _pose_path(name)
    if not path.exists():
        return None
    return {k: float(v) for k, v in json.loads(path.read_text()).items()}


def save_pose(name: str, joints: dict[str, float]) -> Path:
    path = _pose_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: round(v, 2) for k, v in joints.items()}, indent=2) + "\n")
    return path


@dataclass
class Worker:
    """A manipulating arm with its place on the table."""
    arm: Arm
    kinematics: Kinematics
    frame: TableFrame

    def reach(self, table_xy) -> tuple[bool, float]:
        p = self.frame.to_arm(table_xy)
        distance = float(np.hypot(p[0], p[1]))
        if distance > MAX_REACH:
            return False, distance
        q = self.arm.read()
        _, error = self.kinematics.solve_top_down(q, (p[0], p[1], self.frame.z_table + GRASP_M))
        return error <= APPROACH_TOLERANCE, distance

    def _go(self, table_xy, height_m: float, duration: float, log: Log | None = None) -> dict[str, float]:
        p = self.frame.to_arm(table_xy)
        q = self.arm.read()
        target, error = self.kinematics.solve_top_down(q, (p[0], p[1], self.frame.z_table + height_m))
        if error > APPROACH_TOLERANCE:
            raise SkillError(f"{self.arm.role}: cannot reach ({table_xy[0]:+.3f}, {table_xy[1]:+.3f}) "
                             f"at {height_m * 100:.0f} cm (off by {error * 1000:.0f} mm)")
        target["gripper"] = q["gripper"]
        if log:
            log(f"{self.arm.role}: moving to ({table_xy[0]:+.3f}, {table_xy[1]:+.3f}) +{height_m * 100:.0f} cm")
        return self.arm.move_to(target, duration=duration)

    def gripper(self, opening: float, duration: float = 0.6) -> None:
        self.arm.move_to({"gripper": opening}, duration=duration, settle=0.3)

    def ready(self, log: Log | None = None) -> None:
        """A raised pose over the arm's own side of the table, out of the camera's way."""
        pose = load_pose(f"{self.arm.role}.ready")
        if pose is None:
            raise SkillError(f"{self.arm.role}: no ready pose saved")
        if log:
            log(f"{self.arm.role}: ready")
        self.arm.move_to(pose, duration=2.0)

    def pick(self, table_xy, log: Log | None = None) -> None:
        self._go(table_xy, HOVER_M, 2.0, log)
        self.gripper(GRIPPER_OPEN)
        self._go(table_xy, GRASP_M, 1.5, log)
        self.gripper(GRIPPER_CLOSED, duration=0.8)
        self._go(table_xy, HOVER_M, 1.2, log)

    def place(self, table_xy, log: Log | None = None) -> None:
        self._go(table_xy, HOVER_M, 2.0, log)
        self._go(table_xy, DROP_M, 1.2, log)
        self.gripper(GRIPPER_OPEN)
        self._go(table_xy, HOVER_M, 1.0, log)

    def pick_and_place(self, source_xy, destination_xy, log: Log | None = None) -> None:
        self.pick(source_xy, log)
        self.place(destination_xy, log)
        self.ready(log)
        self.gripper(GRIPPER_CLOSED + 6)

    def rest(self) -> None:
        self.arm.rest()


@dataclass
class Head:
    """The camera arm: it holds one steady viewpoint over the table."""
    arm: Arm

    def look(self, log: Log | None = None) -> None:
        pose = load_pose("head.survey")
        if pose is None:
            raise SkillError("head: no survey pose saved")
        if log:
            log("head: taking up the survey pose")
        self.arm.move_to(pose, duration=2.5)
        time.sleep(0.4)

    def rest(self) -> None:
        self.arm.rest()
