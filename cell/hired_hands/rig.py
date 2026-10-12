"""The arms as the cell sees them: roles, boards, joint signs, and one driver per arm.

Every arm is driven in the model frame, the frame of the kinematic model and of every saved pose. The
wrist_flex servo is mounted the other way round on two of the arms, so a per-arm sign flips that joint on
the way in and on the way out; nothing above this module needs to know which arm it is holding.
"""
from __future__ import annotations

import contextlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lerobot.motors.feetech.tables import STS_SMS_SERIES_CONTROL_TABLE as FEETECH_TABLE
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from .config import settings

ROLES = ("left", "head", "right")
JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
ARM_JOINTS = JOINTS[:5]
TELEMETRY = {
    "voltage": ("Present_Voltage", 0.1),
    "temperature": ("Present_Temperature", 1.0),
    "load": ("Present_Load", 1.0),
    "current": ("Present_Current", 1.0),
}


@dataclass(frozen=True)
class ArmSpec:
    role: str
    board: str
    signs: dict[str, int] = field(default_factory=dict)
    camera: bool = False

    @property
    def port(self) -> str:
        return f"/dev/tty.usbmodem{self.board}"


def load_rig(path: Path | None = None) -> dict[str, ArmSpec]:
    path = path or settings().rig_file
    raw = json.loads(path.read_text())
    rig = {}
    for role in ROLES:
        if role not in raw:
            continue
        entry = raw[role]
        rig[role] = ArmSpec(
            role=role,
            board=str(entry["board"]),
            signs={j: int(s) for j, s in entry.get("signs", {}).items() if int(s) == -1},
            camera=bool(entry.get("camera", False)),
        )
    return rig


def rest_pose(role: str) -> dict[str, float] | None:
    path = settings().state_dir / "poses" / f"{role}.rest.json"
    if not path.exists():
        return None
    return {k: float(v) for k, v in json.loads(path.read_text()).items() if k in JOINTS}


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class Arm:
    """One SO-101, spoken to in the model frame, with slow interpolated moves."""

    def __init__(self, spec: ArmSpec, calibration_dir: Path | None = None):
        self.spec = spec
        self.role = spec.role
        self._signs = spec.signs
        self.observer: Callable[[str, dict[str, float]], None] | None = None  # sees joints as they move
        self.observe_every = 6
        self._robot = SO101Follower(
            SO101FollowerConfig(
                id=spec.role,
                port=spec.port,
                calibration_dir=calibration_dir or settings().state_dir / "calibration",
                use_degrees=True,
                disable_torque_on_disconnect=True,
            )
        )

    @property
    def connected(self) -> bool:
        return self._robot.is_connected

    def connect(self, attempts: int = 4) -> None:
        """A marginal supply can leave a servo with a latched protection flag, which the bus reports as an
        error on the next read. Clear the flags and try again rather than give up on the arm."""
        last: Exception | None = None
        calibrated = False
        for attempt in range(attempts):
            try:
                self._robot.connect(calibrate=False)
                calibrated = self._robot.is_calibrated
                break
            except Exception as exc:
                last = exc
                with contextlib.suppress(Exception):
                    self._robot.bus.disconnect(disable_torque=False)
                self._clear_faults()
                time.sleep(0.6 * (attempt + 1))
        else:
            raise RuntimeError(f"{self.role}: could not connect ({last})")
        if not calibrated:
            self._robot.disconnect()
            raise RuntimeError(
                f"{self.role}: the servos do not match {self._robot.calibration_fpath}; refusing to drive them"
            )

    def _clear_faults(self) -> None:
        """Torque off, park the goal on the present position, torque on: the sequence that clears a latched
        fault without the joint lurching. Done at the packet level, below the bus's own error handling."""
        bus = self._robot.bus
        try:
            bus._connect(handshake=False)
        except Exception:
            return
        t_addr, t_len = FEETECH_TABLE["Torque_Enable"]
        g_addr, g_len = FEETECH_TABLE["Goal_Position"]
        p_addr, p_len = FEETECH_TABLE["Present_Position"]
        for name, motor in bus.motors.items():
            bus._write(t_addr, t_len, motor.id, 0, num_retry=3, raise_on_error=False)
            time.sleep(0.05)
            here, _, _ = bus._read(p_addr, p_len, motor.id, num_retry=3, raise_on_error=False)
            if here:
                bus._write(g_addr, g_len, motor.id, int(here), num_retry=3, raise_on_error=False)
            bus._write(t_addr, t_len, motor.id, 1, num_retry=3, raise_on_error=False)
        with contextlib.suppress(Exception):
            bus.disconnect(disable_torque=False)

    def disconnect(self) -> None:
        if self._robot.is_connected:
            self._robot.disconnect()

    def _flip(self, values: dict[str, float]) -> dict[str, float]:
        return {k: (-v if k in self._signs else v) for k, v in values.items()}

    def read(self) -> dict[str, float]:
        for attempt in range(3):
            try:
                obs = self._robot.get_observation()
                return self._flip({k.removesuffix(".pos"): float(v) for k, v in obs.items() if k.endswith(".pos")})
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(0.05)
        raise RuntimeError(f"{self.role}: no reading")

    def write(self, targets: dict[str, float]) -> None:
        for attempt in range(3):
            try:
                self._robot.send_action({f"{k}.pos": v for k, v in self._flip(targets).items()})
                return
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(0.05)

    def move_to(self, targets: dict[str, float], duration: float = 1.5, hz: float = 30.0,
                settle: float = 0.25) -> dict[str, float]:
        """Glide from the present pose to `targets` (joints not listed hold still)."""
        start = self.read()
        self._observe(start)
        goal = {**start, **{k: float(v) for k, v in targets.items() if k in JOINTS}}
        steps = max(1, int(math.ceil(duration * hz)))
        period = 1.0 / hz
        for i in range(1, steps + 1):
            t0 = time.perf_counter()
            a = _smoothstep(i / steps)
            step = {k: start[k] + (goal[k] - start[k]) * a for k in goal}
            self.write(step)
            if i % self.observe_every == 0:
                self._observe(step)
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))
        if settle:
            time.sleep(settle)
        final = self.read()
        self._observe(final)
        return final

    def _observe(self, joints: dict[str, float]) -> None:
        if self.observer is not None:
            try:
                self.observer(self.role, joints)
            except Exception:
                pass  # a watcher must never stop a move

    def rest(self, duration: float = 2.5) -> None:
        pose = rest_pose(self.role)
        if pose:
            self.move_to(pose, duration=duration)

    def telemetry(self) -> dict[str, dict[str, float]]:
        """Per-servo supply voltage (V), temperature (C), load and current, straight from the bus."""
        out: dict[str, dict[str, float]] = {j: {} for j in JOINTS}
        for key, (register, scale) in TELEMETRY.items():
            try:
                values = self._robot.bus.sync_read(register, normalize=False)
            except Exception:  # a register this firmware lacks is not a fault
                continue
            for joint, raw in values.items():
                out[joint][key] = float(raw) * scale
        return out

    def torque(self, enabled: bool) -> None:
        if enabled:
            self._robot.bus.enable_torque()
        else:
            self._robot.bus.disable_torque()
