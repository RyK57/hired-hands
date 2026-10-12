"""The arms measure the table themselves. One arm holds a bright object and shows it to the camera at
known points of its own reach; that fixes where the camera's pixels land. The other arm does the same and
the camera places it on the same map. No printed target is needed.

The table frame is the first arm's base frame turned flat: x forward from its base, y to its left, in metres.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .camera import Camera
from .kinematics import MAX_REACH, Kinematics, TableFrame
from .perception import SATURATION_MIN, VALUE_MIN
from .rig import Arm
from .skills import GRIPPER_CLOSED, Head
from .table import TableMap, reachable_area

Log = Callable[[str], None]

SHOW_HEIGHT_M = 0.03        # the held object hovers this far above the table while the camera looks
SHOW_POINTS = ((0.16, 0.00), (0.22, 0.08), (0.22, -0.08), (0.14, 0.10), (0.14, -0.10), (0.26, 0.00))
MIN_POINTS = 4
MIN_BLOB_PX = 120


class CalibrationError(RuntimeError):
    pass


@dataclass
class Sighting:
    arm_xy: tuple[float, float]
    pixel: tuple[float, float]
    hue: float


def largest_blob(image: np.ndarray, hue: float | None = None, tolerance: float = 14.0) -> tuple[tuple[float, float], float, int] | None:
    """Centre, hue and area of the biggest saturated region, optionally only near a given hue."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, SATURATION_MIN, VALUE_MIN), (180, 255, 255))
    if hue is not None:
        lo, hi = (hue - tolerance) % 180, (hue + tolerance) % 180
        band = cv2.inRange(hsv[..., 0], int(lo), int(hi)) if lo < hi else \
            cv2.bitwise_or(cv2.inRange(hsv[..., 0], int(lo), 180), cv2.inRange(hsv[..., 0], 0, int(hi)))
        mask = cv2.bitwise_and(mask, band)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = int(stats[i, cv2.CC_STAT_AREA])
    if area < MIN_BLOB_PX:
        return None
    cx, cy = centroids[i]
    return (float(cx), float(cy)), float(np.median(hsv[..., 0][labels == i])), area


def measure_table_height(arm: Arm, kin: Kinematics, ask: Callable[[str], None]) -> float:
    """The tip height when the held object rests on the table, measured by hand with torque off."""
    arm.torque(False)
    ask(f"{arm.role}: put a bright object between the jaws and close them on it by hand. Lower the arm until "
        "the object rests on the table, then press Enter.")
    z = float(kin.tip(arm.read())[2])
    arm.torque(True)
    time.sleep(0.3)
    return z


def show_points(arm: Arm, kin: Kinematics, camera: Camera, z_table: float, log: Log,
                to_pixel_hue: float | None = None) -> list[Sighting]:
    """Carry the held object to each show point and record where the camera sees it."""
    sightings: list[Sighting] = []
    hue = to_pixel_hue
    for x, y in SHOW_POINTS:
        if math.hypot(x, y) > MAX_REACH:
            continue
        q = arm.read()
        target, error = kin.solve_top_down(q, (x, y, z_table + SHOW_HEIGHT_M))
        if error > 0.006:
            log(f"{arm.role}: ({x:+.2f}, {y:+.2f}) out of reach, skipped")
            continue
        target["gripper"] = GRIPPER_CLOSED
        arm.move_to(target, duration=2.0, settle=0.6)
        frame = camera.read(settle_frames=8)
        found = largest_blob(frame, hue)
        if found is None:
            log(f"{arm.role}: ({x:+.2f}, {y:+.2f}) nothing bright in view, skipped")
            continue
        pixel, seen_hue, area = found
        if hue is None:
            hue = seen_hue
        actual = kin.tip(arm.read())
        sightings.append(Sighting(arm_xy=(float(actual[0]), float(actual[1])), pixel=pixel, hue=seen_hue))
        log(f"{arm.role}: ({actual[0]:+.3f}, {actual[1]:+.3f}) seen at pixel ({pixel[0]:.0f}, {pixel[1]:.0f}), {area} px")
    return sightings


def fit_camera(sightings: list[Sighting]) -> tuple[np.ndarray, float]:
    """Pixels -> table metres from what the anchor arm showed the camera."""
    if len(sightings) < MIN_POINTS:
        raise CalibrationError(f"only {len(sightings)} sightings; need {MIN_POINTS}")
    src = np.array([s.pixel for s in sightings], dtype=np.float32)
    dst = np.array([s.arm_xy for s in sightings], dtype=np.float32)
    h, _ = cv2.findHomography(src, dst, cv2.RANSAC, 0.012)
    if h is None:
        raise CalibrationError("the sightings do not fit a flat table; check the object stayed in the jaws")
    back = cv2.perspectiveTransform(src.reshape(-1, 1, 2), h).reshape(-1, 2)
    error = float(np.max(np.linalg.norm(back - dst, axis=1)))
    return h, error


def place_arm(sightings: list[Sighting], homography: np.ndarray, z_table: float) -> tuple[TableFrame, float]:
    """Where a second arm stands on the table, from where the camera saw its object."""
    if len(sightings) < 3:
        raise CalibrationError(f"only {len(sightings)} sightings; need 3")
    px = np.array([s.pixel for s in sightings], dtype=np.float32).reshape(-1, 1, 2)
    table = cv2.perspectiveTransform(px, homography).reshape(-1, 2)
    frame = TableFrame.fit([s.arm_xy for s in sightings], table.tolist(), z_table)
    error = float(max(np.linalg.norm(frame.to_table(s.arm_xy) - t) for s, t in zip(sightings, table)))
    return frame, error


def calibrate_rig(arms: dict[str, Arm], head: Head, camera: Camera, kin: Kinematics, *, anchor: str = "left",
                  ask: Callable[[str], None] = input, log: Log = print) -> TableMap:
    """Measure the camera and every working arm in one sitting. The table must be clear of other objects."""
    workers = [r for r in ("left", "right") if r in arms]
    if anchor not in workers:
        raise CalibrationError(f"the anchor arm {anchor!r} is not connected")
    head.look(log)

    heights = {r: measure_table_height(arms[r], kin, ask) for r in workers}
    log("table height: " + ", ".join(f"{r} {heights[r]:+.3f} m" for r in workers))

    anchor_seen = show_points(arms[anchor], kin, camera, heights[anchor], log)
    homography, cam_error = fit_camera(anchor_seen)
    log(f"camera fitted from {len(anchor_seen)} sightings, worst error {cam_error * 1000:.0f} mm")
    arms[anchor].rest()
    frames = {anchor: TableFrame(origin=(0.0, 0.0), yaw=0.0, z_table=heights[anchor])}

    for role in workers:
        if role == anchor:
            continue
        seen = show_points(arms[role], kin, camera, heights[role], log, to_pixel_hue=None)
        frame, error = place_arm(seen, homography, heights[role])
        log(f"{role} stands at ({frame.origin[0]:+.3f}, {frame.origin[1]:+.3f}) m, turned "
            f"{math.degrees(frame.yaw):+.0f} deg; worst error {error * 1000:.0f} mm")
        frames[role] = frame
        arms[role].rest()

    bases = {r: (f.origin[0], f.origin[1], f.yaw) for r, f in frames.items()}
    area = reachable_area(bases, MAX_REACH)
    for role, frame in frames.items():
        frame.save(role)
    table = TableMap(homography=homography, work_area=area, anchor=anchor, bases=bases, fit_error_m=cam_error)
    table.save()
    log(f"work area x {area[0][0]:+.2f}..{area[1][0]:+.2f}, y {area[0][1]:+.2f}..{area[1][1]:+.2f} m")
    head.rest()
    return table
