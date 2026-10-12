"""The job API: hire the cell with one paid request, then watch the job."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from . import evm
from .jobs import JOB_PRICE_DROPS, Cell, Job
from .paywall import LocalLane, PaymentOption, Paywall, RemoteLane, protect, settlement_of
from .x402 import Facilitator, Hirer

AUSD_PRICE = 5.0   # dollars per job


class JobRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=200)
    requester: str | None = Field(default=None, max_length=80)


class VoiceOrder(BaseModel):
    instruction: str = Field(min_length=3, max_length=200)
    caller: str | None = Field(default=None, max_length=80)


def create_app(cell: Cell, *, price_drops: int = JOB_PRICE_DROPS, ausd_price: float = AUSD_PRICE,
               public_url: str | None = None, voice=None) -> FastAPI:
    cfg = settings()
    app = FastAPI(title="Hired Hands", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["*"], expose_headers=["PAYMENT-RESPONSE", "PAYMENT-REQUIRED"])

    facilitator = Facilitator(cell.ledger)
    app.mount("/facilitator", facilitator.app)
    options = [
        PaymentOption(network=cfg.network_id, asset="XRP", amount=str(int(price_drops)),
                      pay_to=cell.ledger.address("treasury"), label=f"XRP on the XRP Ledger ({cfg.network})"),
        PaymentOption(network=evm.NETWORK, asset=evm.AUSD["address"], amount=evm.to_atomic(ausd_price),
                      pay_to=evm.Wallets().address("treasury"), label="AUSD on Base Sepolia",
                      extra={"name": evm.AUSD["name"], "version": evm.AUSD["version"],
                             "assetTransferMethod": "eip3009"}),
    ]
    paywall = Paywall(
        path="/jobs", description="One pick-and-place job on the Hired Hands workcell", options=options,
        lanes={cfg.network_id: LocalLane(facilitator.app, cfg.explorer_tx),
               evm.NETWORK: RemoteLane(evm.FACILITATOR_URL, evm.explorer_tx)},
        invoiced_networks=(cfg.network_id,),
    )
    protect(app, paywall)
    base = (public_url or f"http://{cfg.api_host}:{cfg.api_port}").rstrip("/")
    app.state.accepts = paywall.accepts(f"{base}/jobs")

    @app.get("/")
    def index() -> dict[str, Any]:
        return {
            "name": "Hired Hands",
            "version": __version__,
            "network": cfg.network_id,
            "price_drops": price_drops,
            "arms": {role: {"state": "connected", "health": cell.health.get(role).to_dict() if cell.health.get(role) else None}
                     for role in cell.arms},
            "accepts": app.state.accepts,
            "dashboard": cell.dashboard_url,
        }

    @app.post("/jobs", status_code=202)
    async def create_job(body: JobRequest, request: Request) -> dict[str, Any]:
        settlement = settlement_of(request)
        if settlement is None:
            raise HTTPException(status_code=402, detail="payment required")
        job = Job(instruction=body.instruction.strip(), requester=body.requester, payer=settlement.payer,
                  payment_tx=settlement.tx_hash, price_drops=price_drops, paid=settlement)
        cell.submit(job)
        out = job.summary()
        if cell.dashboard_url:
            out["dashboard"] = f"{cell.dashboard_url.rstrip('/')}/jobs/{job.id}"
        return out

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = cell.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return job.summary()

    @app.get("/arms")
    def arms() -> dict[str, Any]:
        return {role: {"health": h.to_dict()} for role, h in cell.health.items()}

    @app.get("/camera.mjpg")
    async def camera_stream():
        """The head camera, live, as motion JPEG."""
        import cv2

        async def frames():
            while True:
                try:
                    with cell._lock:
                        frame = cell.camera.read(settle_frames=0)
                    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                               + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                except Exception:
                    pass
                await asyncio.sleep(0.12)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.post("/jobs/house")
    async def house_job(body: JobRequest) -> dict[str, Any]:
        """A job placed from the dashboard: the house account pays through the same door as everyone else."""
        hirer = Hirer(cell.ledger.wallet("client"), ledger=cell.ledger)
        local = f"http://127.0.0.1:{cfg.api_port}/jobs"
        response, receipt = await asyncio.to_thread(
            hirer.post, local, {"instruction": body.instruction, "requester": body.requester or "dashboard"})
        if response.status_code >= 300:
            raise HTTPException(status_code=response.status_code, detail=response.text[:200])
        job = response.json()
        job["receipt"] = receipt
        return job

    @app.post("/voice/jobs")
    async def voice_job(body: VoiceOrder, x_voice_key: str | None = Header(default=None)) -> dict[str, Any]:
        """Orders placed by the voice front desk; the house account pays for them like any other hirer."""
        if voice is None or not voice.authorized(x_voice_key):
            raise HTTPException(status_code=401, detail="not the front desk")
        hirer = Hirer(cell.ledger.wallet("client"), ledger=cell.ledger)
        local = f"http://127.0.0.1:{cfg.api_port}/jobs"
        response, receipt = await asyncio.to_thread(
            hirer.post, local, {"instruction": body.instruction, "requester": body.caller or "voice"})
        if response.status_code >= 300:
            return {"error": response.json().get("detail", response.text) if response.headers.get("content-type", "").startswith("application/json") else response.text}
        job = response.json()
        return {
            "job_id": job["id"], "short_id": job["id"][:8], "status": job["status"],
            "price_xrp": round(job["price_drops"] / 1e6, 2),
            "paid_with": (receipt or {}).get("transaction", "")[:12],
            "dashboard": job.get("dashboard"),
        }

    return app
