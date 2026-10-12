"""The workcell: three arms, a camera, a ledger, and the path every job takes from payment to settlement."""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .bidding import Bid, choose, quote
from .camera import Camera, CameraError
from .config import settings
from .events import Publisher
from .health import Health, assess
from .kinematics import Kinematics, TableFrame
from .ledger import batch, credentials, did, escrow
from .ledger.client import Ledger
from .paywall import Settlement
from .perception import Scene, SceneError, observe
from .rig import ROLES, Arm, load_rig
from .selector import Plan, SelectionError, plan as make_plan
from . import takes
from .skills import Head, SkillError, Worker
from .verifier import Verdict, verify

log = logging.getLogger(__name__)

JOB_PRICE_DROPS = 5_000_000
VERIFIER_FEE = 0.05          # of the job price, to the head arm for watching and releasing
OPERATOR_FEE = 0.05          # of the job price, to the operator
HEALTH_EVERY_S = 20.0
CREDENTIAL_TTL_S = 15 * 60


class JobError(RuntimeError):
    pass


@dataclass
class Job:
    instruction: str
    requester: str | None = None
    payer: str | None = None
    payment_tx: str | None = None
    price_drops: int = JOB_PRICE_DROPS
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "paid"
    worker: str | None = None
    plan: Plan | None = None
    bids: list[Bid] = field(default_factory=list)
    escrow: escrow.Escrow | None = None
    verdict: Verdict | None = None
    error: str | None = None
    teleop: bool = False
    paid: Settlement | None = None
    scene: str | None = None
    created_at: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id, "status": self.status, "instruction": self.instruction, "price_drops": self.price_drops,
            "worker": self.worker, "payer": self.payer, "payment_tx": self.payment_tx,
            "paid": self.paid.to_dict() if self.paid else None,
            "escrow_tx": self.escrow.tx_hash if self.escrow else None,
            "verdict": self.verdict.to_dict() if self.verdict else None, "error": self.error,
        }


class Cell:
    def __init__(self, *, ledger: Ledger | None = None, publisher: Publisher | None = None,
                 camera: Camera | None = None, dashboard_url: str | None = None):
        self.ledger = ledger or Ledger()
        self.publisher = publisher or Publisher()
        self.camera = camera or Camera()
        self.dashboard_url = dashboard_url
        self.kinematics = Kinematics()
        self.rig = load_rig()
        self.arms: dict[str, Arm] = {}
        self.workers: dict[str, Worker] = {}
        self.head: Head | None = None
        self.health: dict[str, Health] = {}
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._secrets: dict[str, bytes] = {}   # the head's escrow secrets, by job
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.teleop = None                     # set by the operator when a human can take over
        self.scene: str | None = None          # a recorded skill to use for every job, when set

    # -- lifecycle --------------------------------------------------------------------------------

    def start(self) -> None:
        for role in ROLES:
            spec = self.rig.get(role)
            if spec is None:
                continue
            arm = Arm(spec)
            arm.observer = self._on_joints
            try:
                arm.connect()
            except Exception as exc:
                log.warning("%s: not connected (%s)", role, exc)
                self.publisher.arm(role, state="offline", board=spec.board)
                continue
            self.arms[role] = arm
            if spec.camera:
                self.head = Head(arm)
            else:
                frame = TableFrame.load(role)
                if frame is None:
                    log.warning("%s: no table frame calibrated; it cannot take jobs", role)
                else:
                    self.workers[role] = Worker(arm, self.kinematics, frame)
        for role in self.arms:
            self.publisher.arm(role, state="idle", board=self.rig[role].board, address=self.ledger.address(role),
                               did=did.did_for(self.ledger.address(role)), joints=self.arms[role].read())
        from .table import TableMap
        table = TableMap.load()
        if table is not None:
            self.publisher.cell(layout=table.layout())
        threading.Thread(target=self._health_loop, name="health", daemon=True).start()
        threading.Thread(target=self._job_loop, name="jobs", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for arm in self.arms.values():
            try:
                arm.rest()
                arm.disconnect()
            except Exception:
                pass
        self.publisher.cell(online=False)
        for role in self.arms:
            self.publisher.arm(role, state="offline")
        self.publisher.flush()

    def _on_joints(self, role: str, joints: dict[str, float]) -> None:
        self.publisher.arm(role, joints={k: round(v, 1) for k, v in joints.items()})

    # -- health and credentials ---------------------------------------------------------------------

    def _refresh_health(self) -> None:
        operator = self.ledger.wallet("operator")
        for role, arm in self.arms.items():
            with self._lock:
                try:
                    health = assess(arm.telemetry())
                except Exception as exc:
                    health = Health(score=0.0, voltage=0.0, temperature=0.0, servos_ok=0, reasons=[str(exc)])
            self.health[role] = health
            address = self.ledger.address(role)
            held = credentials.find(self.ledger, address, operator.address, credentials.HEALTH)
            state = credentials.status(held)
            try:
                if health.fit and state in ("none", "expired"):
                    if state == "expired":  # an expired credential stays on the ledger until it is deleted
                        credentials.revoke(self.ledger, operator, address, credentials.HEALTH)
                    issued = credentials.issue(self.ledger, operator, address, credentials.HEALTH,
                                               expires_in_s=CREDENTIAL_TTL_S)
                    credentials.accept(self.ledger, self.ledger.wallet(role), operator.address, credentials.HEALTH)
                    state = "valid"
                    self.publisher.event("credential.renewed" if held else "credential.issued",
                                         f"{role} is fit for work: health {health.score:.2f}", arm_role=role,
                                         tx_hash=issued.hash)
                elif not health.fit and state in ("valid", "pending"):
                    revoked = credentials.revoke(self.ledger, operator, address, credentials.HEALTH)
                    state = "revoked"
                    self.publisher.event("credential.revoked", f"{role} is unfit: {'; '.join(health.reasons)}",
                                         arm_role=role, tx_hash=revoked.hash)
            except Exception as exc:
                log.warning("%s: credential update failed: %s", role, exc)
            self.publisher.arm(role, health=health.to_dict(), health_score=health.score, credential=state,
                               balance_drops=self.ledger.balance(address))

    def _health_loop(self) -> None:
        """The first reading happens right away so the API never waits on the ledger to come up."""
        while True:
            try:
                self._refresh_health()
            except Exception as exc:
                log.warning("health refresh failed: %s", exc)
            if self._stop.wait(HEALTH_EVERY_S):
                return

    # -- jobs -----------------------------------------------------------------------------------------

    def submit(self, job: Job) -> Job:
        self.jobs[job.id] = job
        paid = job.paid
        self.publisher.job(job.id, instruction=job.instruction, requester=job.requester, status=job.status,
                           price_drops=job.price_drops, payer_address=job.payer, payment_tx=job.payment_tx,
                           paid_network=paid.network if paid else None, paid_asset=paid.label if paid else None,
                           paid_amount=paid.amount if paid else None, payment_url=paid.explorer_url if paid else None)
        message = f"job paid: \"{job.instruction}\"" + (f" ({paid.label})" if paid else "")
        if paid and paid.explorer_url and not paid.explorer_url.startswith(settings().explorer_url):
            self.publisher.event("job.paid", message, job_id=job.id, meta={"explorer_url": paid.explorer_url,
                                 "transaction": paid.tx_hash, "amount": paid.amount, "asset": paid.label})
        else:
            self.publisher.event("job.paid", message, job_id=job.id, tx_hash=job.payment_tx, amount_drops=job.price_drops)
        self._queue.put(job)
        return job

    def _job_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.run(job)
            except Exception as exc:
                log.exception("job %s crashed", job.id)
                self._fail(job, str(exc))

    def _set(self, job: Job, status: str, **fields: Any) -> None:
        job.status = status
        self.publisher.job(job.id, status=status, **fields)

    def _arm_state(self, role: str, state: str) -> None:
        self.publisher.arm(role, state=state)

    def _look(self, job: Job, label: str) -> Scene:
        if self.head is None:
            raise JobError("the head arm is not connected")
        with self._lock:
            self.head.look(lambda m: self.publisher.event("survey", m, job_id=job.id, arm_role="head"))
            frame = self.camera.read()
        scene = observe(frame)
        path = settings().captures_dir / f"{job.id}-{label}.jpg"
        import cv2
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), scene.annotated(), [cv2.IMWRITE_JPEG_QUALITY, 88])
        url = self.publisher.upload(path, f"{job.id}/{label}.jpg")
        self.publisher.job(job.id, **{f"{label}_image_url": url})
        self.publisher.event("survey", f"head sees {len(scene.candidates)} object(s): "
                             + ", ".join(c.label for c in scene.candidates), job_id=job.id, arm_role="head",
                             meta={"candidates": [c.to_dict() for c in scene.candidates], "markers": scene.markers})
        return scene

    def run(self, job: Job) -> None:
        # 1. look
        self._set(job, "surveying")
        self._arm_state("head", "surveying")
        try:
            before = self._look(job, "before")
        except (SceneError, CameraError, SkillError) as exc:
            self._arm_state("head", "idle")
            return self._fail(job, f"could not survey the table: {exc}")
        self._arm_state("head", "idle")

        # 2. decide what the instruction means
        try:
            job.plan = make_plan(job.instruction, before)
        except SelectionError as exc:
            return self._fail(job, str(exc))
        self.publisher.job(job.id, target={**job.plan.target.to_dict()}, destination=job.plan.destination.to_dict())
        self.publisher.event("selection", f"target: {job.plan.target.label}; destination: "
                             + (f"object {job.plan.destination.index}" if job.plan.destination.index
                                else f"({job.plan.destination.table[0]:+.2f}, {job.plan.destination.table[1]:+.2f})")
                             + f" [{job.plan.method}: {job.plan.reason}]", job_id=job.id, arm_role="head")

        # 3. bid
        job.scene = self.scene or (None if job.plan.destination.table is not None and self.workers
                                   else takes.match_scene(job.instruction))
        self._set(job, "bidding")
        job.bids = self._collect_bids(job)
        winner = choose(job.bids)
        if winner is None:
            return self._fail(job, "no arm can do this job: " + "; ".join(f"{b.role}: {b.reason}" for b in job.bids))
        job.worker = winner.role
        self.publisher.event("bid.won", f"{winner.role} wins at {winner.price_drops / 1e6:.2f} XRP ({winner.reason})",
                             job_id=job.id, arm_role=winner.role, amount_drops=winner.price_drops)
        self.publisher.job(job.id, worker_role=winner.role)

        # 4. lock the pay
        secret = escrow.new_secret()
        self._secrets[job.id] = secret
        job.escrow = escrow.lock(self.ledger, self.ledger.wallet("treasury"), self.ledger.address(winner.role),
                                 winner.price_drops, secret, cancel_after_s=1800)
        self._set(job, "escrowed", escrow_tx=job.escrow.tx_hash, escrow_sequence=job.escrow.sequence,
                  condition=job.escrow.condition)
        self.publisher.event("job.escrowed", f"{winner.price_drops / 1e6:.2f} XRP locked for {winner.role}; "
                             "only the head can release it", job_id=job.id, tx_hash=job.escrow.tx_hash,
                             amount_drops=winner.price_drops)

        # 5. work
        self._set(job, "working")
        self._arm_state(winner.role, "working")
        worker = self.workers.get(winner.role)
        try:
            with self._lock:
                if job.scene is not None:
                    self._perform(job, winner.role)
                elif worker is not None:
                    worker.pick_and_place(job.plan.target.centre_table, job.plan.destination.table,
                                          log=lambda m: self.publisher.event("pick" if "moving" in m else "place", m,
                                                                             job_id=job.id, arm_role=winner.role))
                else:
                    raise SkillError(f"{winner.role} has neither a table frame nor a recorded skill")
        except (SkillError, RuntimeError, FileNotFoundError) as exc:
            self.publisher.event("error", str(exc), job_id=job.id, arm_role=winner.role)
            if worker is None or not self._hand_over(job, worker):
                self._arm_state(winner.role, "idle")
                return self._fail(job, str(exc))
        self._arm_state(winner.role, "idle")

        # 6. look again and judge
        self._set(job, "verifying")
        self._arm_state("head", "verifying")
        try:
            after = self._look(job, "after")
        except (SceneError, CameraError, SkillError) as exc:
            self._arm_state("head", "idle")
            return self._fail(job, f"could not verify: {exc}")
        job.verdict = verify(before, after, job.plan)
        self.publisher.job(job.id, verdict=job.verdict.to_dict())
        self.publisher.event("verify", ("done: " if job.verdict.ok else "not done: ") + job.verdict.reason,
                             job_id=job.id, arm_role="head")
        if not job.verdict.ok and not job.teleop and worker is not None and self._hand_over(job, worker):
            after = self._look(job, "after")
            job.verdict = verify(before, after, job.plan)
            self.publisher.job(job.id, verdict=job.verdict.to_dict())
            self.publisher.event("verify", ("done: " if job.verdict.ok else "not done: ") + job.verdict.reason,
                                 job_id=job.id, arm_role="head")
        self._arm_state("head", "idle")
        if not job.verdict.ok:
            return self._fail(job, job.verdict.reason)

        # 7. release and settle
        released = escrow.release(self.ledger, self.ledger.wallet("head"), job.escrow, secret)
        self.publisher.event("escrow.release", f"head released {winner.price_drops / 1e6:.2f} XRP to {winner.role}",
                             job_id=job.id, arm_role="head", tx_hash=released.hash, amount_drops=winner.price_drops)
        settlement = self._settle(job, winner)
        self._set(job, "done", release_tx=released.hash, settlement_tx=settlement.hash if settlement else None,
                  finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._after_job(winner.role, winner.price_drops)
        with self._lock:
            for arm in self.arms.values():
                arm.rest()

    def _collect_bids(self, job: Job) -> list[Bid]:
        assert job.plan is not None
        bids = []
        ceiling = int(job.price_drops * (1 - VERIFIER_FEE - OPERATOR_FEE))
        recorded = set(takes.load_scene(job.scene)) if job.scene else set()
        for role in ("left", "right"):
            if role not in self.arms:
                continue
            self._arm_state(role, "bidding")
            worker = self.workers.get(role)
            if job.scene is None and worker is not None and job.plan.target.centre_table is not None:
                with self._lock:
                    can_reach, reach_m = worker.reach(job.plan.target.centre_table)
                    if can_reach and job.plan.destination.table is not None:
                        can_reach, reach_dest = worker.reach(job.plan.destination.table)
                        reach_m = max(reach_m, reach_dest)
            else:
                can_reach = role in recorded
                reach_m = 0.18 if can_reach else 0.0
            debt = self._debt(role)
            bid = quote(role, can_reach=can_reach, reach_m=reach_m, health=self.health.get(role) or
                        Health(0.0, 0.0, 0.0, 0, ["no health reading"]), debt_drops=debt, ceiling_drops=ceiling)
            if not can_reach and job.scene is not None and role not in recorded:
                bid = Bid(role, False, 0.0, bid.health_score, 0, f"no recorded skill for '{job.scene}'")
            bids.append(bid)
            self.publisher.bid(job.id, arm_role=role, price_drops=bid.price_drops, reach_m=bid.reach_m,
                               health_score=bid.health_score, feasible=bid.feasible, reason=bid.reason)
            self.publisher.event("bid", f"{role}: " + (f"{bid.price_drops / 1e6:.2f} XRP, {bid.reason}" if bid.feasible
                                                      else f"passes ({bid.reason})"), job_id=job.id, arm_role=role,
                                 amount_drops=bid.price_drops if bid.feasible else None)
            self._arm_state(role, "idle")
        return bids

    def _perform(self, job: Job, lead: str) -> None:
        """Play the recorded skill: every arm with a take in the scene moves, together."""
        assert job.scene is not None
        cast = {r: a for r, a in self.arms.items()}
        for role in cast:
            if role != lead:
                self._arm_state(role, "working")
        self.publisher.event("pick", f"{lead} runs the recorded skill '{job.scene}'"
                             + (" with " + ", ".join(r for r in takes.load_scene(job.scene) if r != lead and r in cast)
                                if len(takes.load_scene(job.scene)) > 1 else ""), job_id=job.id, arm_role=lead)
        durations = takes.play(cast, job.scene, log=lambda m: log.info(m))
        self.publisher.event("place", f"skill finished in {max(durations.values()):.1f} s", job_id=job.id, arm_role=lead)
        for role in cast:
            if role != lead:
                self._arm_state(role, "idle")

    def _debt(self, role: str) -> int:
        lending = getattr(self, "lending", None)
        return lending.outstanding(role) if lending else 0

    def _settle(self, job: Job, winner: Bid):
        treasury = self.ledger.wallet("treasury")
        transfers = [
            batch.payment(treasury, self.ledger.address("head"), int(job.price_drops * VERIFIER_FEE)),
            batch.payment(treasury, self.ledger.address("operator"), int(job.price_drops * OPERATOR_FEE)),
        ]
        cosigners = []
        lending = getattr(self, "lending", None)
        repayment = None
        if lending is not None:
            repayment = lending.repayment(winner.role, winner.price_drops)
            if repayment is not None:
                transfers.append(repayment.transaction)
                cosigners.append(self.ledger.wallet(winner.role))
        try:
            done = batch.settle(self.ledger, treasury, transfers, cosigners)
        except Exception as exc:
            self.publisher.event("error", f"settlement failed: {exc}", job_id=job.id)
            return None
        message = (f"settled in one batch: {VERIFIER_FEE:.0%} to head, {OPERATOR_FEE:.0%} to the operator"
                   + (f", {repayment.amount_drops / 1e6:.2f} XRP of {winner.role}'s loan repaid" if repayment else ""))
        self.publisher.event("settlement", message, job_id=job.id, tx_hash=done.hash,
                             amount_drops=int(job.price_drops * (VERIFIER_FEE + OPERATOR_FEE)))
        if repayment is not None:
            lending.record_payment(job.id, winner.role, repayment, done.hash)
        return done

    def _after_job(self, role: str, earned_drops: int) -> None:
        arm_row = {"jobs_done": self._count_done(role), "earned_drops": self._earned(role),
                   "balance_drops": self.ledger.balance(self.ledger.address(role))}
        self.publisher.arm(role, **arm_row)
        self.publisher.arm("head", balance_drops=self.ledger.balance(self.ledger.address("head")))

    def _count_done(self, role: str) -> int:
        return sum(1 for j in self.jobs.values() if j.worker == role and j.status == "done")

    def _earned(self, role: str) -> int:
        return sum(j.escrow.amount_drops for j in self.jobs.values()
                   if j.worker == role and j.status == "done" and j.escrow)

    def _hand_over(self, job: Job, worker: Worker) -> bool:
        """Let a human finish the job when one is available. Returns True when they did."""
        if self.teleop is None or job.teleop:
            return False
        job.teleop = True
        self._set(job, "teleop", teleop=True)
        self._arm_state(worker.arm.role, "teleop")
        try:
            with self._lock:
                self.teleop(job, worker)
        except Exception as exc:
            self.publisher.event("error", f"operator session ended: {exc}", job_id=job.id, arm_role=worker.arm.role)
            self._arm_state(worker.arm.role, "idle")
            return False
        self._arm_state(worker.arm.role, "idle")
        self._set(job, "verifying")
        return True

    def _fail(self, job: Job, reason: str) -> None:
        job.error = reason
        self._set(job, "failed", error=reason)
        self.publisher.event("error", reason, job_id=job.id)
        if job.payer and job.payment_tx:
            try:
                if job.paid is not None and job.paid.network != settings().network_id:
                    from . import evm
                    tx_hash = evm.refund(job.payer, job.paid.amount)
                    self._set(job, "refunded")
                    self.publisher.event("job.refunded", f"{evm.from_atomic(job.paid.amount):.2f} AUSD returned to the hirer",
                                         job_id=job.id, meta={"explorer_url": evm.explorer_tx(tx_hash), "transaction": tx_hash})
                else:
                    refund = self.ledger.submit(batch.payment(self.ledger.wallet("treasury"), job.payer, job.price_drops),
                                                self.ledger.wallet("treasury"))
                    self._set(job, "refunded")
                    self.publisher.event("job.refunded", f"{job.price_drops / 1e6:.2f} XRP returned to the hirer",
                                         job_id=job.id, tx_hash=refund.hash, amount_drops=job.price_drops)
            except Exception as exc:
                self.publisher.event("error", f"refund failed: {exc}", job_id=job.id)
        with self._lock:
            for arm in self.arms.values():
                try:
                    arm.rest()
                except Exception:
                    pass
