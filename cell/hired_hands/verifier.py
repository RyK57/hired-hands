"""Was the job done? The head arm looks again and compares what it sees with what was asked."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .perception import Candidate, Scene
from .selector import Plan

PLACED_WITHIN_M = 0.035       # the target's centre must end up this close to the destination
CONTAINED_WITHIN_M = 0.045    # or this close to another object's centre when put in or on it
MOVED_AT_LEAST_M = 0.03       # and it must have moved from where it started
PLACED_WITHIN_PX = 55         # the same three, in pixels, for a table that has not been measured
CONTAINED_WITHIN_PX = 70
MOVED_AT_LEAST_PX = 35


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


def _position(c: Candidate, mapped: bool) -> tuple[float, float]:
    return c.centre_table if mapped and c.centre_table else c.centre_px


def _nearest(colour: str, candidates: list[Candidate], to: tuple[float, float], mapped: bool) -> Candidate | None:
    same = [c for c in candidates if c.colour == colour]
    if not same:
        return None
    return min(same, key=lambda c: math.dist(_position(c, mapped), to))


def verify(before: Scene, after: Scene, plan: Plan) -> Verdict:
    mapped = before.mapped and after.mapped and plan.destination.table is not None
    unit, scale = ("cm", 100.0) if mapped else ("px", 1.0)
    placed, contained, moved_min = ((PLACED_WITHIN_M, CONTAINED_WITHIN_M, MOVED_AT_LEAST_M) if mapped
                                    else (PLACED_WITHIN_PX, CONTAINED_WITHIN_PX, MOVED_AT_LEAST_PX))
    target_was = _position(plan.target, mapped)
    destination = plan.destination.table if mapped else plan.destination.px
    if destination is None:
        return Verdict(False, "the destination has no position to check against")
    found = _nearest(plan.target.colour, after.candidates, destination, mapped)

    if found is None:
        if plan.destination.index is not None:
            # dropped inside something that now hides it: the destination must still be there, the target gone
            holder = _nearest(plan.destination.colour or "", after.candidates, destination, mapped)
            if holder is not None and math.dist(_position(holder, mapped), destination) < contained:
                return Verdict(True, f"the {plan.target.colour} object is no longer visible and the "
                                     f"{plan.destination.colour} one is still in place: it went inside")
        return Verdict(False, f"no {plan.target.colour} object is visible any more")

    position = _position(found, mapped)
    distance = math.dist(position, destination)
    moved = math.dist(position, target_was)
    limit = contained if plan.destination.index is not None else placed
    if plan.destination.index is not None and moved >= moved_min:
        # inside the destination's outline counts, however big the destination is
        holder = _nearest(plan.destination.colour or "", after.candidates, destination, mapped)
        if holder is not None:
            x0, y0, w, h = holder.bbox
            px, py = found.centre_px
            if x0 - 12 <= px <= x0 + w + 12 and y0 - 12 <= py <= y0 + h + 12:
                return Verdict(True, f"the {plan.target.colour} object is inside the {holder.colour} one",
                               distance if mapped else None, moved if mapped else None)
    if distance <= limit and (moved >= moved_min or math.dist(target_was, destination) < moved_min):
        return Verdict(True, f"the {plan.target.colour} object is {distance * scale:.0f} {unit} from the destination",
                       distance if mapped else None, moved if mapped else None)
    if moved < moved_min:
        return Verdict(False, f"the {plan.target.colour} object did not move", distance if mapped else None,
                       moved if mapped else None)
    return Verdict(False, f"the {plan.target.colour} object ended {distance * scale:.0f} {unit} from the destination",
                   distance if mapped else None, moved if mapped else None)
