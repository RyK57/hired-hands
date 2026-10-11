"""The `hands` command: run the cell, set it up, calibrate it, and hire it."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .config import settings


def _log() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore", "hpack", "lerobot"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# -- serve ----------------------------------------------------------------------------------------

def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .api import create_app
    from .events import Publisher
    from .jobs import JOB_PRICE_DROPS, Cell

    cfg = settings()
    publisher = Publisher()
    cell = Cell(publisher=publisher, dashboard_url=args.dashboard)
    cell.start()
    if args.teleop:
        from .teleop import Operator
        cell.teleop = Operator(cell)
    price = int(args.price * 1_000_000) if args.price else JOB_PRICE_DROPS
    public_url = args.public_url or cfg.public_url
    app = create_app(cell, price_drops=price, public_url=public_url)
    publisher.cell(
        network=cfg.network, network_id=cfg.network_id, explorer_url=cfg.explorer_url, online=True,
        api_url=public_url or f"http://{cfg.api_host}:{cfg.api_port}", accepts=app.state.accepts,
        operator_address=cell.ledger.address("operator"), treasury_address=cell.ledger.address("treasury"),
        broker_address=cell.ledger.address("broker"),
    )
    print(f"Hired Hands on {cfg.network}: {len(cell.workers)} worker arm(s), head {'ready' if cell.head else 'absent'}; "
          f"{price / 1e6:.2f} XRP per job; API on port {cfg.api_port}")
    try:
        uvicorn.run(app, host=cfg.api_host, port=cfg.api_port, log_level="warning")
    finally:
        cell.stop()


# -- setup ----------------------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> None:
    from .ledger import did, domain, credentials
    from .ledger.client import WALLETS, Ledger

    cfg = settings()
    ledger = Ledger()
    print(f"network: {cfg.network} ({cfg.rpc_url})")
    for name in WALLETS:
        wallet = ledger.wallet(name)
        print(f"  {name:12s} {wallet.address}  {ledger.balance(wallet.address) / 1e6:10.3f} XRP")
    operator = ledger.wallet("operator")
    for role in ("left", "head", "right"):
        page = f"{args.dashboard.rstrip('/')}/arms/{role}" if args.dashboard else None
        done = did.publish(ledger, ledger.wallet(role), role, page_url=page)
        print(f"  did    {role:6s} {did.did_for(ledger.address(role))}  {done.hash[:12]}")
    existing = domain.find(ledger, operator.address)
    if existing:
        print(f"  domain {existing[:16]}… (already set)")
    else:
        done, domain_id = domain.create(ledger, operator, [(operator.address, credentials.DEPOSITOR)])
        print(f"  domain {domain_id[:16]}…  {done.hash[:12]}")


def cmd_wallets(args: argparse.Namespace) -> None:
    from .ledger.client import WALLETS, Ledger
    ledger = Ledger()
    for name in WALLETS:
        if ledger.has_wallet(name):
            address = ledger.address(name)
            print(f"{name:12s} {address}  {ledger.balance(address) / 1e6:10.3f} XRP  {settings().explorer_account(address)}")


# -- hardware -------------------------------------------------------------------------------------

def _arm(role: str):
    from .rig import Arm, load_rig
    rig = load_rig()
    if role not in rig:
        sys.exit(f"no arm with role {role!r} in {settings().rig_file}")
    arm = Arm(rig[role])
    arm.connect()
    return arm


def cmd_board(args: argparse.Namespace) -> None:
    from .board import render_sheet
    out = render_sheet(Path(args.path))
    print(f"wrote {out}; print it at 100 % scale, landscape")


def cmd_pose(args: argparse.Namespace) -> None:
    from .skills import save_pose
    arm = _arm(args.role)
    arm.torque(False)
    print(f"{args.role}: torque is off. Move the arm into the pose by hand, then press Enter.")
    input()
    joints = arm.read()
    path = save_pose(args.name, joints)
    print(f"saved {args.name}: " + ", ".join(f"{k}={v:.1f}" for k, v in joints.items()) + f"\n  -> {path}")
    arm.disconnect()


def cmd_calibrate(args: argparse.Namespace) -> None:
    import numpy as np

    from .board import MARKERS
    from .kinematics import Kinematics, TableFrame

    kin = Kinematics()
    arm = _arm(args.role)
    arm.torque(False)
    print(f"{args.role}: torque is off. Close the gripper by hand and rest its tip on each marker's centre.")
    arm_points, table_points = [], []
    for marker_id, centre in MARKERS.items():
        input(f"  tip on the centre of marker {marker_id} at ({centre[0]:+.3f}, {centre[1]:+.3f}) -> Enter")
        tip = kin.tip(arm.read())
        arm_points.append(tip[:2])
        table_points.append(centre)
        print(f"    arm frame ({tip[0]:+.3f}, {tip[1]:+.3f}, {tip[2]:+.3f})")
    input("  tip resting flat on the table inside the work area -> Enter")
    z_table = float(kin.tip(arm.read())[2])
    frame = TableFrame.fit(arm_points, table_points, z_table)
    residuals = [float(np.linalg.norm(frame.to_table(a) - np.asarray(t))) for a, t in zip(arm_points, table_points)]
    path = frame.save(args.role)
    print(f"base at ({frame.origin[0]:+.3f}, {frame.origin[1]:+.3f}) m, yaw {np.degrees(frame.yaw):+.1f} deg, "
          f"table z {z_table:+.3f} m; fit error {max(residuals) * 1000:.1f} mm -> {path}")
    arm.disconnect()


def cmd_survey(args: argparse.Namespace) -> None:
    import cv2

    from .camera import Camera
    from .perception import observe
    from .skills import Head, load_pose

    head = None
    if not args.no_move:
        head = Head(_arm("head"))
        head.look(print)
    with Camera() as camera:
        frame = camera.read()
    scene = observe(frame)
    out = settings().captures_dir / "survey.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), scene.annotated())
    print(f"markers {scene.markers}; {len(scene.candidates)} object(s):")
    for c in scene.candidates:
        print(f"  {c.label:12s} at ({c.centre_table[0]:+.3f}, {c.centre_table[1]:+.3f}) m, {c.area_px} px")
    print(f"-> {out}")
    if head is not None:
        if args.rest:
            head.rest()
        head.arm.disconnect()


def cmd_health(args: argparse.Namespace) -> None:
    from .health import assess
    from .rig import load_rig
    for role in load_rig():
        try:
            arm = _arm(role)
        except Exception as exc:
            print(f"{role:6s} offline ({exc})")
            continue
        health = assess(arm.telemetry())
        print(f"{role:6s} score {health.score:.2f}  {health.voltage:.1f} V  {health.temperature:.0f} C  "
              f"{health.servos_ok}/6 servos  {'fit' if health.fit else 'UNFIT'}  {'; '.join(health.reasons)}")
        arm.disconnect()


def cmd_rest(args: argparse.Namespace) -> None:
    from .rig import load_rig
    for role in load_rig():
        try:
            arm = _arm(role)
            arm.rest()
            arm.disconnect()
            print(f"{role}: at rest")
        except Exception as exc:
            print(f"{role}: {exc}")


# -- hire -----------------------------------------------------------------------------------------

def cmd_hire(args: argparse.Namespace) -> None:
    import httpx

    from .ledger.client import Ledger
    from .x402 import Hirer

    ledger = Ledger()
    hirer = Hirer(ledger.wallet(args.wallet), ledger=ledger)
    url = args.url.rstrip("/")
    response, receipt = hirer.post(f"{url}/jobs", {"instruction": args.instruction, "requester": args.requester})
    if response.status_code >= 300:
        sys.exit(f"{response.status_code}: {response.text}")
    job = response.json()
    if receipt:
        print(f"paid {receipt.get('transaction', '')[:12]}… as {receipt.get('payer')}")
    print(f"job {job['id']} {job['status']}" + (f"  {job['dashboard']}" if job.get("dashboard") else ""))
    if args.no_wait:
        return
    last = job["status"]
    while last not in ("done", "failed", "refunded"):
        time.sleep(1.5)
        job = httpx.get(f"{url}/jobs/{job['id']}", timeout=10).json()
        if job["status"] != last:
            last = job["status"]
            print(f"  {last}" + (f": {job['error']}" if job.get("error") else "")
                  + (f" ({job['worker']})" if job.get("worker") and last == "working" else ""))
    if job.get("verdict"):
        print(f"  verdict: {json.dumps(job['verdict'])}")


# -- entry ----------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    _log()
    parser = argparse.ArgumentParser(prog="hands", description="Hired Hands workcell")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the cell and its job API")
    p.add_argument("--price", type=float, help="XRP per job")
    p.add_argument("--public-url", help="where hirers reach the API")
    p.add_argument("--dashboard", help="dashboard URL to link from job responses")
    p.add_argument("--teleop", action="store_true", help="let a human take over when autonomy fails")
    p.set_defaults(run=cmd_serve)

    p = sub.add_parser("setup", help="fund wallets, publish identities, create the vault domain")
    p.add_argument("--dashboard", help="dashboard URL the arms' identities point at")
    p.set_defaults(run=cmd_setup)

    sub.add_parser("wallets", help="list the cell's accounts").set_defaults(run=cmd_wallets)

    p = sub.add_parser("board", help="render the printable work surface")
    p.add_argument("path", nargs="?", default=str(settings().captures_dir / "work-surface.png"))
    p.set_defaults(run=cmd_board)

    p = sub.add_parser("pose", help="save the arm's current pose under a name (left.ready, head.survey, ...)")
    p.add_argument("role", choices=["left", "head", "right"])
    p.add_argument("name")
    p.set_defaults(run=cmd_pose)

    p = sub.add_parser("calibrate", help="measure where an arm sits on the table")
    p.add_argument("role", choices=["left", "right"])
    p.set_defaults(run=cmd_calibrate)

    p = sub.add_parser("survey", help="take a look at the table from the head camera")
    p.add_argument("--no-move", action="store_true", help="use the camera where it is")
    p.add_argument("--rest", action="store_true", help="fold the head afterwards")
    p.set_defaults(run=cmd_survey)

    sub.add_parser("health", help="read every servo and score each arm").set_defaults(run=cmd_health)
    sub.add_parser("rest", help="fold every arm").set_defaults(run=cmd_rest)

    p = sub.add_parser("hire", help="pay for a job and watch it")
    p.add_argument("instruction")
    p.add_argument("--url", default=f"http://127.0.0.1:{settings().api_port}")
    p.add_argument("--wallet", default="client")
    p.add_argument("--requester", default=None)
    p.add_argument("--no-wait", action="store_true")
    p.set_defaults(run=cmd_hire)

    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
