"""Was the job done? The head arm looks again and compares what it sees with what was asked."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .perception import Candidate, Scene
from .selector import Plan

PLACED_WITHIN_M = 0.035       # the target's centre must end up this close to the destination
CONTAINED_WITHIN_M = 0.045    # or this close to another object's centre when put in or on it
MOVED_AT_LEAST_M = 0.03       # and it must have moved from where it started


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str
    distance_m: float | None = None
    moved_m: float | None = None

    def to_dict(self) -> dict:
        d: dict = {"ok": self.ok, "reason": self.reason}
        if self.distance_m is not None:
            d["distance_m"] = round(self.distance_m, 4)
        if self.moved_m is not None:
            d["moved_m"] = round(self.moved_m, 4)
        return d


def _nearest(colour: str, candidates: list[Candidate], to: tuple[float, float]) -> Candidate | None:
    same = [c for c in candidates if c.colour == colour]
    if not same:
        return None
    return min(same, key=lambda c: math.dist(c.centre_table, to))


def verify(before: Scene, after: Scene, plan: Plan) -> Verdict:
    target_was = plan.target.centre_table
    destination = plan.destination.table
    found = _nearest(plan.target.colour, after.candidates, destination)

    if found is None:
        if plan.destination.index is not None:
            # dropped inside something that now hides it: the destination must still be there, the target gone
            holder = _nearest(plan.destination.colour or "", after.candidates, destination)
            if holder is not None and math.dist(holder.centre_table, destination) < CONTAINED_WITHIN_M:
                return Verdict(True, f"the {plan.target.colour} object is no longer visible and the "
                                     f"{plan.destination.colour} one is still in place: it went inside")
        return Verdict(False, f"no {plan.target.colour} object is visible any more")

    distance = math.dist(found.centre_table, destination)
    moved = math.dist(found.centre_table, target_was)
    limit = CONTAINED_WITHIN_M if plan.destination.index is not None else PLACED_WITHIN_M
    if distance <= limit and (moved >= MOVED_AT_LEAST_M or math.dist(target_was, destination) < MOVED_AT_LEAST_M):
        return Verdict(True, f"the {plan.target.colour} object is {distance * 100:.1f} cm from the destination",
                       distance, moved)
    if moved < MOVED_AT_LEAST_M:
        return Verdict(False, f"the {plan.target.colour} object did not move", distance, moved)
    return Verdict(False, f"the {plan.target.colour} object ended {distance * 100:.1f} cm from the destination",
                   distance, moved)
