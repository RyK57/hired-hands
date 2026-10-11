"""Pay-per-job over HTTP. A request without payment is answered with 402 and the cell's payment requirements;
a request carrying a presigned XRP Ledger payment is verified, settled on-ledger and then served.

The cell runs its own facilitator, so no third party sits between a hirer and the arms.
"""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Request
from x402_xrpl.client.presigned_payment_payer import (
    XRPLPresignedPaymentPayer,
    XRPLPresignedPaymentPayerOptions,
    invoice_id_to_invoice_id_field,
    invoice_id_to_memo_hex,
)
from x402_xrpl.server.fastapi import RequireX402Options, require_x402
from x402_xrpl.types import PaymentPayload, PaymentRequired, PaymentRequirements
from xrpl.core.binarycodec import decode
from xrpl.wallet import Wallet

from .config import settings
from .ledger.client import Ledger, LedgerError

PAYMENT_HEADER = "PAYMENT-SIGNATURE"
RECEIPT_HEADER = "PAYMENT-RESPONSE"


@dataclass(frozen=True)
class Settlement:
    invoice_id: str
    payer: str
    tx_hash: str
    amount_drops: int

    def to_dict(self) -> dict[str, Any]:
        return {"invoiceId": self.invoice_id, "payer": self.payer, "transaction": self.tx_hash,
                "amount_drops": self.amount_drops}


def _decode_header(header: str) -> PaymentPayload:
    return PaymentPayload.from_dict(json.loads(base64.b64decode(header)))


def _check(payload: PaymentPayload, req: PaymentRequirements) -> tuple[dict[str, Any], str | None]:
    """The decoded payment transaction and, when something is wrong with it, why."""
    blob = payload.payload.get("signedTxBlob")
    invoice_id = payload.payload.get("invoiceId")
    if not blob or not invoice_id:
        return {}, "missing_payment"
    try:
        tx = decode(blob)
    except Exception:
        return {}, "undecodable_transaction"
    if tx.get("TransactionType") != "Payment":
        return tx, "not_a_payment"
    if req.network != settings().network_id:
        return tx, "wrong_network"
    if tx.get("Destination") != req.pay_to:
        return tx, "wrong_destination"
    if req.asset != "XRP" or not isinstance(tx.get("Amount"), str):
        return tx, "unsupported_asset"
    if int(tx["Amount"]) < int(req.amount):
        return tx, "insufficient_amount"
    if invoice_id != req.invoice_id():
        return tx, "invoice_mismatch"
    bound = tx.get("InvoiceID") == invoice_id_to_invoice_id_field(invoice_id) or any(
        m.get("Memo", {}).get("MemoData") == invoice_id_to_memo_hex(invoice_id) for m in tx.get("Memos", [])
    )
    if not bound:
        return tx, "invoice_not_bound"
    if not tx.get("TxnSignature") or not tx.get("SigningPubKey"):
        return tx, "unsigned"
    return tx, None


class Facilitator:
    """Verifies and settles payments against the cell's own ledger connection. Served in-process for the
    cell's API and mountable on it for anyone else who wants to use it."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.settlements: dict[str, Settlement] = {}
        self.app = FastAPI(title="Hired Hands facilitator")
        self.app.add_api_route("/supported", self._supported, methods=["GET"])
        self.app.add_api_route("/verify", self._verify, methods=["POST"])
        self.app.add_api_route("/settle", self._settle, methods=["POST"])
        self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://facilitator",
                                         timeout=60.0)

    async def _supported(self) -> dict[str, Any]:
        return {"kinds": [{"x402Version": 2, "scheme": "exact", "network": settings().network_id}]}

    @staticmethod
    def _parse(body: dict[str, Any]) -> tuple[PaymentPayload, PaymentRequirements]:
        return PaymentPayload.from_dict(body["paymentPayload"]), PaymentRequirements.from_dict(body["paymentRequirements"])

    async def _verify(self, request: Request) -> dict[str, Any]:
        payload, req = self._parse(await request.json())
        tx, problem = _check(payload, req)
        if problem:
            return {"isValid": False, "invalidReason": problem}
        return {"isValid": True, "payer": tx["Account"]}

    async def _settle(self, request: Request) -> dict[str, Any]:
        payload, req = self._parse(await request.json())
        tx, problem = _check(payload, req)
        if problem:
            return {"success": False, "errorReason": problem, "transaction": "", "network": req.network}
        try:
            done = await asyncio.to_thread(self.ledger.submit_signed, payload.payload["signedTxBlob"])
        except LedgerError as exc:
            return {"success": False, "errorReason": exc.result, "transaction": "", "network": req.network}
        invoice_id = str(payload.payload["invoiceId"])
        self.settlements[invoice_id] = Settlement(invoice_id=invoice_id, payer=tx["Account"], tx_hash=done.hash,
                                                   amount_drops=int(tx["Amount"]))
        return {"success": True, "transaction": done.hash, "network": req.network, "payer": tx["Account"]}

    def settlement_for(self, request: Request) -> Settlement | None:
        """The settled payment that let this request through."""
        header = request.headers.get(PAYMENT_HEADER)
        if not header:
            return None
        try:
            invoice_id = str(_decode_header(header).payload.get("invoiceId"))
        except Exception:
            return None
        return self.settlements.get(invoice_id)


def requirements(*, pay_to: str, price_drops: int, path: str, description: str,
                 facilitator: Facilitator) -> RequireX402Options:
    return RequireX402Options(
        pay_to=pay_to,
        amount=str(int(price_drops)),
        network=settings().network_id,
        asset="XRP",
        path=path,
        description=description,
        facilitator=facilitator,  # type: ignore[arg-type]  (the middleware only needs its HTTP client)
        facilitator_identity={"id": "hired-hands", "name": "Hired Hands"},
    )


def protect(app: FastAPI, options: RequireX402Options) -> None:
    app.middleware("http")(require_x402(options))


def accepts(options: RequireX402Options, resource_url: str) -> list[dict[str, Any]]:
    """The payment options a hirer will be offered, as the dashboard publishes them."""
    return [{
        "scheme": options.scheme, "network": options.network, "asset": options.asset,
        "amount": options.amount, "payTo": options.pay_to, "resource": resource_url,
        "description": options.description, "maxTimeoutSeconds": options.max_timeout_seconds,
    }]


class Hirer:
    """A paying client: posts a request, pays what the 402 asks for, and posts again."""

    def __init__(self, wallet: Wallet, *, ledger: Ledger | None = None):
        cfg = settings()
        self.wallet = wallet
        self._payer = XRPLPresignedPaymentPayer(
            XRPLPresignedPaymentPayerOptions(wallet=wallet, network=cfg.network_id, rpc_url=cfg.rpc_url),  # type: ignore[arg-type]
            client=ledger.client if ledger else None,
        )

    def post(self, url: str, body: dict[str, Any], *, timeout: float = 120.0) -> tuple[httpx.Response, dict | None]:
        """Returns the final response and the settlement receipt the server attached, if it charged."""
        with httpx.Client(timeout=timeout) as http:
            first = http.post(url, json=body)
            if first.status_code != 402:
                return first, None
            required = PaymentRequired.from_dict(first.json())
            option = next((r for r in required.accepts if self._payer.supports(r)), None)
            if option is None:
                raise RuntimeError(f"none of the offered payment options can be paid from this wallet: "
                                   f"{[r.network + '/' + r.asset for r in required.accepts]}")
            header = self._payer.create_payment_header(option, resource=required.resource)
            final = http.post(url, json=body, headers={PAYMENT_HEADER: header})
            receipt = None
            if final.headers.get(RECEIPT_HEADER):
                receipt = json.loads(base64.b64decode(final.headers[RECEIPT_HEADER]))
            return final, receipt
