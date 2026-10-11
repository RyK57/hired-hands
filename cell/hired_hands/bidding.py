"""How an arm prices a job: can it reach the work, how far is it, how fit is it, and how much does it owe."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .health import Health

BASE_DROPS = 1_000_000          # 1 XRP to pick up and put down anything
DISTANCE_DROPS_PER_M = 5_000_000  # reach costs effort
UNFIT_MARKUP_DROPS = 1_000_000  # a tired arm asks for more
DEBT_DISCOUNT = 0.10            # an arm with a loan to repay undercuts to win work
MIN_DROPS = 500_000


@dataclass(frozen=True)
class Bid:
    role: str
    feasible: bool
    reach_m: float
    health_score: float
    price_drops: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "role": self.role, "feasible": self.feasible, "reach_m": round(self.reach_m, 3),
            "health_score": round(self.health_score, 3), "price_drops": self.price_drops, "reason": self.reason,
        }


def quote(role: str, *, can_reach: bool, reach_m: float, health: Health, debt_drops: int,
          ceiling_drops: int) -> Bid:
    """One arm's asking price for a job whose pay is capped at `ceiling_drops`."""
    if not health.fit:
        return Bid(role, False, reach_m, health.score, 0, "; ".join(health.reasons) or "not fit for work")
    if not can_reach:
        return Bid(role, False, reach_m, health.score, 0, f"out of reach at {reach_m * 100:.0f} cm")

    price = BASE_DROPS + DISTANCE_DROPS_PER_M * max(0.0, reach_m - 0.10) + UNFIT_MARKUP_DROPS * (1.0 - health.score)
    reason = f"{reach_m * 100:.0f} cm reach, health {health.score:.2f}"
    if debt_drops > 0:
        price *= 1.0 - DEBT_DISCOUNT
        reason += f", {DEBT_DISCOUNT:.0%} off to pay down {debt_drops / 1e6:.1f} XRP of debt"
    price = int(min(max(price, MIN_DROPS), ceiling_drops))
    return Bid(role, True, reach_m, health.score, price, reason)


def choose(bids: list[Bid]) -> Bid | None:
    """The cheapest feasible bid; ties go to the healthier arm."""
    feasible = [b for b in bids if b.feasible]
    if not feasible:
        return None
    return min(feasible, key=lambda b: (b.price_drops, -b.health_score, math.inf))
