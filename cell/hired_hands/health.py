"""An arm's fitness for work, scored from what its servos report right now."""
from __future__ import annotations

from dataclasses import dataclass, field

from .rig import JOINTS

VOLTAGE_NOMINAL = 5.5    # the rail every arm runs from
VOLTAGE_MIN = 4.8        # below this the servos brown out under load
TEMP_WARM = 45.0
TEMP_HOT = 60.0


@dataclass(frozen=True)
class Health:
    score: float                      # 0..1
    voltage: float                    # lowest servo supply voltage seen (V)
    temperature: float                # hottest servo (C)
    servos_ok: int
    reasons: list[str] = field(default_factory=list)

    @property
    def fit(self) -> bool:
        return self.score >= 0.5 and self.servos_ok == len(JOINTS)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "voltage": round(self.voltage, 2),
            "temperature": round(self.temperature, 1),
            "servos_ok": self.servos_ok,
            "fit": self.fit,
            "reasons": list(self.reasons),
        }


def assess(telemetry: dict[str, dict[str, float]]) -> Health:
    """Score telemetry as `Arm.telemetry()` returns it. A missing servo is the worst thing that can happen."""
    reasons: list[str] = []
    voltages = [t["voltage"] for t in telemetry.values() if "voltage" in t and t["voltage"] > 0]
    temps = [t["temperature"] for t in telemetry.values() if "temperature" in t]
    servos_ok = sum(1 for j in JOINTS if telemetry.get(j, {}).get("voltage", 0) > 0)

    score = 1.0
    missing = len(JOINTS) - servos_ok
    if missing:
        score -= 0.5 * missing
        reasons.append(f"{missing} servo(s) not answering")

    voltage = min(voltages) if voltages else 0.0
    if voltages:
        if voltage < VOLTAGE_MIN:
            score -= 0.4
            reasons.append(f"supply {voltage:.1f} V below {VOLTAGE_MIN} V")
        else:
            score -= 0.2 * max(0.0, (VOLTAGE_NOMINAL - voltage) / (VOLTAGE_NOMINAL - VOLTAGE_MIN))

    temperature = max(temps) if temps else 0.0
    if temps:
        if temperature >= TEMP_HOT:
            score -= 0.4
            reasons.append(f"servo at {temperature:.0f} C")
        elif temperature >= TEMP_WARM:
            score -= 0.15 * (temperature - TEMP_WARM) / (TEMP_HOT - TEMP_WARM)
            reasons.append(f"servo warm ({temperature:.0f} C)")

    return Health(score=max(0.0, min(1.0, score)), voltage=voltage, temperature=temperature,
                  servos_ok=servos_ok, reasons=reasons)
