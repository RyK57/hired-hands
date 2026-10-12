"""Recorded skills: one take per arm, played back together so the arms work as one. A scene is a folder of
takes with the instruction it carries out."""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import settings
from .rig import JOINTS, Arm

PLAY_HZ = 30
LEAD_S = 2.5          # time every arm gets to reach its first frame before the shared start
ROLE_ALIASES = {"follower3": "left", "follower2": "right", "leader": "head"}


def takes_dir() -> Path:
    return settings().state_dir / "takes"


def scene_dir(scene: str) -> Path:
    return takes_dir() / scene


@dataclass(frozen=True)
class Take:
    role: str
    motors: tuple[str, ...]
    frames: np.ndarray          # N x (1 + joints): time since start, then joints in the model frame

    @property
    def duration(self) -> float:
        return float(self.frames[-1, 0] - self.frames[0, 0])

    def resampled(self, duration: float, hz: float = PLAY_HZ) -> np.ndarray:
        """Joints at a steady rate, the whole take stretched or squeezed to `duration` seconds."""
        t = self.frames[:, 0] - self.frames[0, 0]
        if self.duration <= 0:
            return np.repeat(self.frames[:1, 1:], 2, axis=0)
        grid = np.linspace(0.0, t[-1], max(2, int(round(duration * hz))))
        return np.column_stack([np.interp(grid, t, self.frames[:, 1 + i]) for i in range(len(self.motors))])

    def as_dict(self, joints: np.ndarray) -> dict[str, float]:
        return {m: float(v) for m, v in zip(self.motors, joints)}

    @classmethod
    def load(cls, path: Path) -> "Take":
        d = json.loads(path.read_text())
        frames = np.asarray(d["frames"], dtype=float)
        return cls(role=d["role"], motors=tuple(d["motors"]), frames=frames)


def _role_of(raw: str) -> str:
    name = raw.removeprefix("hack_")
    return ROLE_ALIASES.get(name, name)


def import_take(source: Path, scene: str, role: str | None = None) -> Path:
    """Bring a take recorded by the teleop tools into a scene."""
    d = json.loads(source.read_text())
    role = role or _role_of(str(d.get("robot_id", "")))
    if role not in ("left", "head", "right"):
        raise ValueError(f"cannot tell which arm {source.name} belongs to; pass the role")
    motors = list(d["motors"])
    if any(m not in JOINTS for m in motors):
        raise ValueError(f"{source.name} has unknown joints {motors}")
    out = scene_dir(scene) / f"{role}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"role": role, "motors": motors, "frames": d["frames"],
                               "source": source.name, "recorded_at": d.get("recorded_at")}) + "\n")
    return out


def latest_takes(folder: Path, prefix: str = "take") -> dict[str, Path]:
    """The newest recording per arm in a folder of teleop recordings."""
    found: dict[str, Path] = {}
    for path in sorted(folder.glob(f"{prefix}_*_*.json")):
        match = re.match(rf"{re.escape(prefix)}_([a-z0-9]+)_(\d+)\.json$", path.name)
        if not match:
            continue
        role = _role_of(match.group(1))
        if role in ("left", "head", "right"):
            found[role] = path   # sorted ascending, so the last one wins
    return found


def describe(scene: str, instruction: str) -> Path:
    path = scene_dir(scene) / "scene.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"instruction": instruction}, indent=2) + "\n")
    return path


def load_scene(scene: str) -> dict[str, Take]:
    folder = scene_dir(scene)
    takes = {}
    for role in ("left", "head", "right"):
        path = folder / f"{role}.json"
        if path.exists():
            takes[role] = Take.load(path)
    if not takes:
        raise FileNotFoundError(f"no takes in scene {scene!r}")
    return takes


def scenes() -> dict[str, dict]:
    out = {}
    if not takes_dir().exists():
        return out
    for folder in sorted(p for p in takes_dir().iterdir() if p.is_dir()):
        meta = {}
        if (folder / "scene.json").exists():
            meta = json.loads((folder / "scene.json").read_text())
        roles = [r for r in ("left", "head", "right") if (folder / f"{r}.json").exists()]
        if roles:
            out[folder.name] = {"instruction": meta.get("instruction"), "arms": roles}
    return out


def match_scene(instruction: str) -> str | None:
    """The recorded scene whose instruction shares the most words with this one."""
    words = set(re.findall(r"[a-z]+", instruction.lower()))
    best, score = None, 0
    for name, meta in scenes().items():
        theirs = set(re.findall(r"[a-z]+", (meta.get("instruction") or name).lower()))
        overlap = len(words & theirs)
        if overlap > score:
            best, score = name, overlap
    if best is None and len(scenes()) == 1:
        best = next(iter(scenes()))
    return best


def play(arms: dict[str, Arm], scene: str, *, speed: float = 1.0, lead_s: float = LEAD_S,
         log=None) -> dict[str, float]:
    """Every arm that has a take plays it; all start together and finish together."""
    takes = {r: t for r, t in load_scene(scene).items() if r in arms}
    if not takes:
        raise FileNotFoundError(f"none of the connected arms has a take in {scene!r}")
    # the longest take sets the pace: shorter ones are stretched to it, nothing is ever sped up
    duration = float(max(t.duration for t in takes.values())) / max(speed, 0.05)
    frames = {r: t.resampled(duration) for r, t in takes.items()}
    if log:
        log(f"playing '{scene}' on {', '.join(takes)}: {duration:.1f} s")

    ready = threading.Barrier(len(takes))
    errors: dict[str, Exception] = {}

    def run(role: str) -> None:
        arm, take, series = arms[role], takes[role], frames[role]
        try:
            arm.move_to(take.as_dict(series[0]), duration=lead_s, settle=0.0)
            ready.wait(timeout=lead_s + 10)
            period = 1.0 / PLAY_HZ
            t0 = time.perf_counter()
            for i, joints in enumerate(series):
                arm.write(take.as_dict(joints))
                if i % 6 == 0 and arm.observer is not None:
                    arm.observer(role, take.as_dict(joints))
                time.sleep(max(0.0, t0 + (i + 1) * period - time.perf_counter()))
        except Exception as exc:  # one arm failing must not leave the others mid-air
            errors[role] = exc
            try:
                ready.abort()
            except Exception:
                pass

    threads = [threading.Thread(target=run, args=(r,), name=f"take-{r}", daemon=True) for r in takes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        role, exc = next(iter(errors.items()))
        raise RuntimeError(f"{role}: {exc}")
    return {r: duration for r in takes}


def remove(scene: str) -> None:
    shutil.rmtree(scene_dir(scene), ignore_errors=True)


def record(arms: dict[str, Arm], scene: str, *, hz: float = PLAY_HZ, countdown_s: float = 3.0,
           log=print, instruction: str | None = None) -> dict[str, Take]:
    """Record every arm at once while a person moves them by hand. Torque is off during the take and comes
    back when it ends, so the arms hold where they were left."""
    import sys
    import threading

    for arm in arms.values():
        arm.torque(False)
    log(f"torque is off on {', '.join(arms)}. Press Enter to start recording.")
    input()
    for n in range(int(countdown_s), 0, -1):
        log(f"  {n}…")
        time.sleep(1.0)
    log("● recording — move the arms. Press Enter to stop.")

    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()), daemon=True).start()
    frames: dict[str, list[list[float]]] = {r: [] for r in arms}
    t0 = time.perf_counter()
    period = 1.0 / hz
    tick = 0
    while not stop.is_set():
        now = time.perf_counter() - t0
        for role, arm in arms.items():
            try:
                q = arm.read()
            except Exception:
                continue   # a dropped read loses one frame, not the take
            frames[role].append([round(now, 4)] + [round(q[j], 3) for j in JOINTS])
        tick += 1
        if tick % int(hz * 5) == 0:
            log(f"  {now:5.1f} s")
        time.sleep(max(0.0, t0 + tick * period - time.perf_counter()))
    duration = time.perf_counter() - t0
    for arm in arms.values():
        arm.torque(True)

    folder = scene_dir(scene)
    folder.mkdir(parents=True, exist_ok=True)
    takes: dict[str, Take] = {}
    for role, rows in frames.items():
        if len(rows) < 2:
            continue
        (folder / f"{role}.json").write_text(json.dumps({
            "role": role, "motors": list(JOINTS), "frames": rows,
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "by hand",
        }) + "\n")
        takes[role] = Take(role=role, motors=tuple(JOINTS), frames=np.asarray(rows, dtype=float))
    if instruction:
        describe(scene, instruction)
    log(f"saved {duration:.1f} s on {', '.join(takes)} -> {folder}")
    return takes
