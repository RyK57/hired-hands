"""Which numbered object does the instruction mean, and where should it go?

A vision-language model reads the annotated frame when a key is configured; otherwise the colour words in
the instruction decide. Either way the answer is an index into the scene's candidates, never a coordinate
the model made up.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

import cv2

from .table import work_area
from .config import settings
from .perception import HUE_NAMES, Candidate, Scene

COLOURS = sorted({name for _, _, name in HUE_NAMES} | {"white"})
ZONES = {
    "left": (-0.07, 0.0), "right": (0.07, 0.0), "front": (0.0, -0.035), "back": (0.0, 0.035),
    "centre": (0.0, 0.0), "center": (0.0, 0.0), "middle": (0.0, 0.0),
}


@dataclass(frozen=True)
class Spot:
    """A place on the table: another object, or a point. Positions are in table metres when the table has
    been measured, otherwise in image pixels."""
    table: tuple[float, float] | None
    px: tuple[float, float] | None = None
    index: int | None = None
    colour: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"table": [round(self.table[0], 4), round(self.table[1], 4)] if self.table else None,
                   "px": [round(self.px[0], 1), round(self.px[1], 1)] if self.px else None}
        if self.index is not None:
            d["index"] = self.index
        if self.colour is not None:
            d["colour"] = self.colour
        return d

    @classmethod
    def of(cls, candidate: Candidate) -> "Spot":
        return cls(table=candidate.centre_table, px=candidate.centre_px, index=candidate.index, colour=candidate.colour)


@dataclass(frozen=True)
class Plan:
    target: Candidate
    destination: Spot
    method: str
    reason: str


class SelectionError(RuntimeError):
    pass


def _colour_words(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w in COLOURS]


def _zone(text: str, scene: Scene) -> Spot | None:
    words = re.findall(r"[a-z]+", text.lower())
    for w in words:
        if w in ZONES:
            if scene.mapped:
                return Spot(table=ZONES[w])
            h, wdt = scene.image.shape[:2]
            px = {"left": (wdt * 0.2, h * 0.55), "right": (wdt * 0.8, h * 0.55), "front": (wdt * 0.5, h * 0.8),
                  "back": (wdt * 0.5, h * 0.3)}.get(w, (wdt * 0.5, h * 0.55))
            return Spot(table=None, px=px)
    return None


def _by_colour(colour: str, candidates: list[Candidate], exclude: int | None = None,
               centre: tuple[float, float] | None = None) -> Candidate | None:
    """The candidate of this colour; with several, the one closest to the middle of the view."""
    same = [c for c in candidates if c.colour == colour and c.index != exclude]
    if not same:
        return None
    if centre is None:
        return same[0]
    return min(same, key=lambda c: (c.centre_px[0] - centre[0]) ** 2 + (c.centre_px[1] - centre[1]) ** 2)


def plan_by_colour(instruction: str, scene: Scene) -> Plan:
    colours = _colour_words(instruction)
    if not colours:
        raise SelectionError("the instruction names no colour and no model is configured to read the scene")
    h, w = scene.image.shape[:2]
    middle = (w / 2, h / 2)
    target = _by_colour(colours[0], scene.candidates, centre=middle)
    if target is None:
        raise SelectionError(f"no {colours[0]} object is on the table")
    if len(colours) > 1:
        other = _by_colour(colours[1], scene.candidates, exclude=target.index, centre=middle)
        if other is None:
            raise SelectionError(f"no {colours[1]} object is on the table")
        destination = Spot.of(other)
    else:
        destination = _zone(instruction, scene)
        if destination is None:
            raise SelectionError("the instruction says where to pick from but not where to put it")
    return Plan(target=target, destination=destination, method="colour",
                reason=f"matched '{colours[0]}'" + (f" and '{colours[1]}'" if len(colours) > 1 else ""))


_PROMPT = """You are the eyes of a robot workcell. The image shows a work surface seen from above with every object
numbered. The operator's instruction is: "{instruction}"

Objects on the table (number: colour, position in metres):
{listing}

Reply with JSON only:
{{"target": <number of the object to pick up>,
 "destination": <number of the object to put it in or on, or null>,
 "destination_point": [x, y] in metres if the destination is a place rather than an object, else null,
 "reason": "<one short sentence>"}}
The work area spans x from {x0} to {x1} and y from {y0} to {y1} (y grows away from the viewer).
If the instruction cannot be carried out with these objects, reply {{"error": "<why>"}}."""


def plan_by_model(instruction: str, scene: Scene) -> Plan:
    import anthropic

    cfg = settings()
    if not cfg.anthropic_api_key:
        raise SelectionError("no model key configured")
    ok, jpeg = cv2.imencode(".jpg", scene.annotated(), [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise SelectionError("could not encode the frame")
    (x0, y0), (x1, y1) = work_area()
    listing = "\n".join(
        f"{c.index}: {c.colour}, " + (f"({c.centre_table[0]:+.3f}, {c.centre_table[1]:+.3f})" if c.centre_table
                                      else f"pixel ({c.centre_px[0]:.0f}, {c.centre_px[1]:.0f})")
        for c in scene.candidates
    ) or "(none)"
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    response = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(jpeg.tobytes()).decode()}},
                {"type": "text", "text": _PROMPT.format(instruction=instruction, listing=listing,
                                                         x0=x0, x1=x1, y0=y0, y1=y1)},
            ],
        }],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise SelectionError(f"the model gave no answer: {text[:120]}")
    answer = json.loads(match.group(0))
    if "error" in answer:
        raise SelectionError(str(answer["error"]))
    target = scene.find(int(answer["target"]))
    if target is None:
        raise SelectionError(f"the model chose object {answer['target']}, which is not on the table")
    if answer.get("destination") is not None:
        other = scene.find(int(answer["destination"]))
        if other is None:
            raise SelectionError(f"the model chose destination {answer['destination']}, which is not on the table")
        destination = Spot.of(other)
    elif answer.get("destination_point") and scene.mapped:
        x, y = (float(v) for v in answer["destination_point"])
        destination = Spot(table=(min(max(x, x0), x1), min(max(y, y0), y1)))
    elif answer.get("destination_point"):
        raise SelectionError("the destination must be an object until the table has been measured")
    else:
        raise SelectionError("the model named a target but no destination")
    return Plan(target=target, destination=destination, method="model", reason=str(answer.get("reason", "")))


def plan(instruction: str, scene: Scene) -> Plan:
    if not scene.candidates:
        raise SelectionError("nothing is on the table")
    if settings().anthropic_api_key:
        try:
            return plan_by_model(instruction, scene)
        except SelectionError:
            raise
        except Exception:
            pass  # a model outage must not stop the cell; the colour words still work
    return plan_by_colour(instruction, scene)
