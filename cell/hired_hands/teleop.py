"""A human finishes what the arm could not, and is paid by the second over a payment channel."""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from .kinematics import top_down_rotation
from .ledger import paychan
from .skills import GRIPPER_CLOSED, GRIPPER_OPEN, Worker

RATE_DROPS_PER_S = 50_000       # 0.05 XRP for every second at the controls
CHANNEL_DROPS = 3_000_000       # the most one session can earn
STEP_M = 0.004                  # per tick while a key is held
GRIPPER_STEP = 4.0
TICK_HZ = 20.0
MAX_SESSION_S = 180.0

KEYS = {
    "w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0), "r": (0, 0, 1), "f": (0, 0, -1),
}


class Operator:
    """Keyboard control of one arm: W/S forward and back, A/D left and right, R/F up and down,
    O/P open and close the gripper, Esc to hand the job back."""

    def __init__(self, cell) -> None:
        self.cell = cell

    def __call__(self, job, worker: Worker) -> None:
        from pynput import keyboard

        ledger = self.cell.ledger
        publisher = self.cell.publisher
        treasury = ledger.wallet("treasury")
        operator = ledger.wallet("teleoperator")

        channel = paychan.open(ledger, treasury, operator.address, CHANNEL_DROPS, settle_delay_s=60)
        publisher.channel(channel.id, job_id=job.id, operator_address=operator.address, amount_drops=CHANNEL_DROPS,
                          status="open", open_tx=channel.open_tx)
        publisher.event("channel.open", f"payment channel opened for a human operator: up to "
                        f"{CHANNEL_DROPS / 1e6:.0f} XRP at {RATE_DROPS_PER_S / 1e6:.2f} XRP/s",
                        job_id=job.id, arm_role=worker.arm.role, tx_hash=channel.open_tx)
        publisher.event("teleop.start", f"a human has the controls of {worker.arm.role}", job_id=job.id,
                        arm_role=worker.arm.role)

        pressed: set[str] = set()
        done = threading.Event()

        def on_press(key) -> None:
            if key == keyboard.Key.esc:
                done.set()
                return
            name = getattr(key, "char", None)
            if name:
                pressed.add(name.lower())

        def on_release(key) -> None:
            name = getattr(key, "char", None)
            if name:
                pressed.discard(name.lower())

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        arm, kin = worker.arm, worker.kinematics
        joints = arm.read()
        pose = kin.pose(joints)
        target = pose[:3, 3].copy()
        gripper = joints["gripper"]
        started = time.time()
        last_claim = None
        last_second = 0
        period = 1.0 / TICK_HZ
        try:
            while not done.is_set() and time.time() - started < MAX_SESSION_S:
                t0 = time.perf_counter()
                delta = np.zeros(3)
                for key in pressed:
                    if key in KEYS:
                        delta += np.array(KEYS[key], dtype=float)
                if "o" in pressed:
                    gripper = min(GRIPPER_OPEN + 20, gripper + GRIPPER_STEP)
                if "p" in pressed:
                    gripper = max(GRIPPER_CLOSED, gripper - GRIPPER_STEP)
                if np.any(delta) or "o" in pressed or "p" in pressed:
                    target = target + delta * STEP_M
                    azimuth = math.atan2(target[1], target[0])
                    goal = np.eye(4)
                    goal[:3, :3] = top_down_rotation(azimuth)
                    goal[:3, 3] = target
                    solved, error = kin.solve(joints, goal, iterations=8)
                    if error < 0.01:
                        solved["gripper"] = gripper
                        arm.write(solved)
                        joints = solved
                    else:
                        target = target - delta * STEP_M  # stay where the arm can still reach
                seconds = int(time.time() - started)
                if seconds > last_second:
                    last_second = seconds
                    earned = min(CHANNEL_DROPS, seconds * RATE_DROPS_PER_S)
                    last_claim = paychan.authorize(treasury, channel, earned)
                    publisher.channel(channel.id, claimed_drops=earned, seconds_driven=seconds)
                    if seconds % 5 == 0:
                        publisher.event("channel.claim", f"{seconds} s at the controls: {earned / 1e6:.2f} XRP signed over",
                                        job_id=job.id, arm_role=arm.role, amount_drops=earned)
                time.sleep(max(0.0, period - (time.perf_counter() - t0)))
        finally:
            listener.stop()
            pressed.clear()

        publisher.event("teleop.stop", f"the human handed {arm.role} back after {last_second} s", job_id=job.id,
                        arm_role=arm.role)
        if last_claim is not None and last_claim.amount_drops > 0:
            redeemed = paychan.redeem(ledger, operator, last_claim, close=True)
            publisher.channel(channel.id, status="closed", close_tx=redeemed.hash,
                              closed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            publisher.event("channel.claim", f"operator redeemed {last_claim.amount_drops / 1e6:.2f} XRP and "
                            "closed the channel", job_id=job.id, tx_hash=redeemed.hash,
                            amount_drops=last_claim.amount_drops)
        worker.ready()
