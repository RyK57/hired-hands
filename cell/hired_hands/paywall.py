"""Pay-per-job over HTTP. A request without payment is answered with 402 and every way the cell accepts
payment; a request carrying a payment is verified, settled on the chain it chose, and only then served.

XRP on the XRP Ledger settles through the cell's own facilitator. AUSD on Base settles through a public one.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

import httpx
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

PAYMENT_HEADER = "PAYMENT-SIGNATURE"
REQUIRED_HEADER = "PAYMENT-REQUIRED"
RECEIPT_HEADER = "PAYMENT-RESPONSE"
INVOICE_TTL_S = 900


@dataclass(frozen=True)
class PaymentOption:
    network: str
    asset: str
    amount: str
    pay_to: str
    label: str
    extra: dict[str, Any] = field(default_factory=dict)
    scheme: str = "exact"
    max_timeout_seconds: int = 600

    def requirements(self, **extra: Any) -> dict[str, Any]:
        return {
            "scheme": self.scheme, "network": self.network, "asset": self.asset, "amount": self.amount,
            "payTo": self.pay_to, "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": {**self.extra, **extra},
        }

    def matches(self, accepted: dict[str, Any]) -> bool:
        return all(accepted.get(k) == v for k, v in (
            ("scheme", self.scheme), ("network", self.network), ("asset", self.asset),
            ("amount", self.amount), ("payTo", self.pay_to)))

    def to_dict(self, resource_url: str) -> dict[str, Any]:
        return {**self.requirements(), "label": self.label, "resource": resource_url}


@dataclass(frozen=True)
class Settlement:
    network: str
    asset: str
    amount: str
    payer: str
    tx_hash: str
    label: str
    explorer_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"network": self.network, "asset": self.asset, "amount": self.amount, "payer": self.payer,
                "transaction": self.tx_hash, "label": self.label, "explorerUrl": self.explorer_url}


class Lane(Protocol):
    """One way of verifying and settling a payment on one network."""

    async def verify(self, payload: dict[str, Any], requirements: dict[str, Any]) -> tuple[bool, str | None, str | None]: ...

    async def settle(self, payload: dict[str, Any], requirements: dict[str, Any]) -> tuple[bool, str | None, str | None, str | None]: ...

    def explorer(self, tx_hash: str) -> str | None: ...


class RemoteLane:
    """A facilitator somebody else runs, spoken to over HTTP."""

    def __init__(self, url: str, explorer_tx: Callable[[str], str] | None = None):
        self.url = url.rstrip("/")
        self._explorer = explorer_tx
        self._client = httpx.AsyncClient(timeout=90.0)

    @staticmethod
    def _body(payload: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
        return {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": requirements}

    async def verify(self, payload, requirements):
        response = await self._client.post(f"{self.url}/verify", json=self._body(payload, requirements))
        if response.status_code != 200:
            return False, f"facilitator_http_{response.status_code}", None
        data = response.json()
        return bool(data.get("isValid")), data.get("invalidReason"), data.get("payer")

    async def settle(self, payload, requirements):
        response = await self._client.post(f"{self.url}/settle", json=self._body(payload, requirements))
        if response.status_code != 200:
            return False, None, None, f"facilitator_http_{response.status_code}"
        data = response.json()
        return bool(data.get("success")), data.get("transaction") or None, data.get("payer"), data.get("errorReason")

    def explorer(self, tx_hash: str) -> str | None:
        return self._explorer(tx_hash) if self._explorer else None


class LocalLane(RemoteLane):
    """A facilitator served in this process."""

    def __init__(self, app: FastAPI, explorer_tx: Callable[[str], str] | None = None):
        super().__init__("http://facilitator", explorer_tx)
        self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://facilitator",
                                         timeout=90.0)


class Paywall:
    def __init__(self, *, path: str, description: str, options: list[PaymentOption], lanes: dict[str, Lane],
                 invoiced_networks: tuple[str, ...] = ()):
        self.path = path
        self.description = description
        self.options = options
        self.lanes = lanes
        self.invoiced = set(invoiced_networks)
        self._invoices: dict[str, float] = {}

    # -- the 402 -----------------------------------------------------------------------------------

    def accepts(self, resource_url: str) -> list[dict[str, Any]]:
        return [o.to_dict(resource_url) for o in self.options]

    def _required(self, request: Request) -> JSONResponse:
        now = time.time()
        self._invoices = {k: v for k, v in self._invoices.items() if v > now}
        invoice_id = uuid.uuid4().hex.upper()
        self._invoices[invoice_id] = now + INVOICE_TTL_S
        accepts = [
            o.requirements(invoiceId=invoice_id) if o.network in self.invoiced else o.requirements()
            for o in self.options
        ]
        body = {
            "x402Version": 2,
            "error": "payment required",
            "resource": {"url": str(request.url), "description": self.description, "mimeType": "application/json"},
            "accepts": accepts,
            "extensions": {},
        }
        encoded = base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
        return JSONResponse(status_code=402, content=body, headers={REQUIRED_HEADER: encoded})

    # -- the payment --------------------------------------------------------------------------------

    def _match(self, accepted: dict[str, Any]) -> tuple[PaymentOption | None, dict[str, Any] | None, str | None]:
        option = next((o for o in self.options if o.matches(accepted)), None)
        if option is None:
            return None, None, "unknown_payment_option"
        extra: dict[str, Any] = {}
        if option.network in self.invoiced:
            invoice_id = (accepted.get("extra") or {}).get("invoiceId")
            if not invoice_id or self._invoices.get(invoice_id, 0) < time.time():
                return option, None, "unknown_or_expired_invoice"
            extra["invoiceId"] = invoice_id
        return option, option.requirements(**extra), None

    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path != self.path or request.method != "POST":
            return await call_next(request)
        header = request.headers.get(PAYMENT_HEADER)
        if not header:
            return self._required(request)
        try:
            envelope = json.loads(base64.b64decode(header))
            accepted = dict(envelope["accepted"])
        except Exception:
            return JSONResponse(status_code=400, content={"error": "malformed_payment"})
        option, requirements, problem = self._match(accepted)
        if option is None or requirements is None:
            return JSONResponse(status_code=402, content={"error": problem})
        lane = self.lanes.get(option.network)
        if lane is None:
            return JSONResponse(status_code=402, content={"error": "no_lane_for_network"})

        valid, reason, payer = await lane.verify(envelope, requirements)
        if not valid:
            return JSONResponse(status_code=402, content={"error": f"verify_failed:{reason}"})
        settled, tx_hash, settled_payer, reason = await lane.settle(envelope, requirements)
        if not settled or not tx_hash:
            return JSONResponse(status_code=402, content={"error": f"settle_failed:{reason}"})
        if "invoiceId" in requirements.get("extra", {}):
            self._invoices.pop(requirements["extra"]["invoiceId"], None)

        settlement = Settlement(network=option.network, asset=option.asset, amount=option.amount,
                                payer=settled_payer or payer or "", tx_hash=tx_hash, label=option.label,
                                explorer_url=lane.explorer(tx_hash))
        request.state.settlement = settlement
        response = await call_next(request)
        receipt = {"success": True, "network": option.network, "transaction": tx_hash, "payer": settlement.payer}
        response.headers[RECEIPT_HEADER] = base64.b64encode(json.dumps(receipt, separators=(",", ":")).encode()).decode()
        return response


def protect(app: FastAPI, paywall: Paywall) -> None:
    app.middleware("http")(paywall)


def settlement_of(request: Request) -> Settlement | None:
    return getattr(request.state, "settlement", None)
