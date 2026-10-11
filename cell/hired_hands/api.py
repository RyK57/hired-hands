"""The job API: hire the cell with one paid request, then watch the job."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from .jobs import JOB_PRICE_DROPS, Cell, Job
from .x402 import Facilitator, accepts, protect, requirements


class JobRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=200)
    requester: str | None = Field(default=None, max_length=80)


def create_app(cell: Cell, *, price_drops: int = JOB_PRICE_DROPS, public_url: str | None = None) -> FastAPI:
    cfg = settings()
    app = FastAPI(title="Hired Hands", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["*"], expose_headers=["PAYMENT-RESPONSE"])

    facilitator = Facilitator(cell.ledger)
    options = requirements(pay_to=cell.ledger.address("treasury"), price_drops=price_drops, path="/jobs",
                           description="One pick-and-place job on the Hired Hands workcell", facilitator=facilitator)
    protect(app, options)
    app.mount("/facilitator", facilitator.app)
    base = (public_url or f"http://{cfg.api_host}:{cfg.api_port}").rstrip("/")
    app.state.accepts = accepts(options, f"{base}/jobs")

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
        settlement = facilitator.settlement_for(request)
        if settlement is None:
            raise HTTPException(status_code=402, detail="payment required")
        job = Job(instruction=body.instruction.strip(), requester=body.requester, payer=settlement.payer,
                  payment_tx=settlement.tx_hash, price_drops=settlement.amount_drops)
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

    return app
