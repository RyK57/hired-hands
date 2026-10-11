"""The XRP Ledger side of x402: the cell's own facilitator, which verifies and settles presigned payments
against its ledger connection, and the client that pays a 402 in XRP or in AUSD."""
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
from x402_xrpl.types import PaymentPayload, PaymentRequired, PaymentRequirements
from xrpl.core.binarycodec import decode
from xrpl.wallet import Wallet

from .config import settings
from .ledger.client import Ledger, LedgerError

try:
    from eth_account.signers.local import LocalAccount
except ImportError:  # pragma: no cover
    LocalAccount = Any  # type: ignore[misc,assignment]

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


class Hirer:
    """A paying client: posts a request, pays whichever option it was told to prefer, and posts again."""

    def __init__(self, wallet: Wallet | None = None, *, ledger: Ledger | None = None,
                 account: "LocalAccount | None" = None, prefer: str = "xrp"):
        cfg = settings()
        self.prefer = prefer
        self._payer = None
        if wallet is not None:
            self._payer = XRPLPresignedPaymentPayer(
                XRPLPresignedPaymentPayerOptions(wallet=wallet, network=cfg.network_id, rpc_url=cfg.rpc_url),  # type: ignore[arg-type]
                client=ledger.client if ledger else None,
            )
        self._account = account

    def _xrpl_header(self, required: PaymentRequired) -> str | None:
        if self._payer is None:
            return None
        option = next((r for r in required.accepts if self._payer.supports(r)), None)
        if option is None:
            return None
        return self._payer.create_payment_header(option, resource=required.resource)

    def _evm_header(self, body: dict[str, Any]) -> str | None:
        if self._account is None:
            return None
        from .evm import NETWORK, transfer_authorization
        option = next((a for a in body.get("accepts", []) if a.get("network") == NETWORK and a.get("scheme") == "exact"), None)
        if option is None:
            return None
        payload = transfer_authorization(self._account, option)
        envelope = {"x402Version": 2, "resource": body.get("resource"), "accepted": option, "payload": payload}
        return base64.b64encode(json.dumps(envelope, separators=(",", ":")).encode()).decode()

    def post(self, url: str, body: dict[str, Any], *, timeout: float = 180.0) -> tuple[httpx.Response, dict | None]:
        """Returns the final response and the settlement receipt the server attached, if it charged."""
        with httpx.Client(timeout=timeout) as http:
            first = http.post(url, json=body)
            if first.status_code != 402:
                return first, None
            required_body = first.json()
            doors = [self._evm_header, lambda b: self._xrpl_header(PaymentRequired.from_dict(b))]
            if self.prefer == "xrp":
                doors.reverse()
            header = None
            for door in doors:
                try:
                    header = door(required_body)
                except Exception:
                    header = None
                if header:
                    break
            if header is None:
                raise RuntimeError("none of the offered payment options can be paid from this hirer's wallets: "
                                   + ", ".join(f"{a.get('network')}/{a.get('asset')}" for a in required_body.get("accepts", [])))
            final = http.post(url, json=body, headers={PAYMENT_HEADER: header})
            receipt = None
            if final.headers.get(RECEIPT_HEADER):
                receipt = json.loads(base64.b64decode(final.headers[RECEIPT_HEADER]))
            return final, receipt
