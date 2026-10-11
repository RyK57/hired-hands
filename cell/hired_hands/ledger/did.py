"""Decentralised identifiers: each arm publishes who it is and where to read about it, from its own account."""
from __future__ import annotations

import json

from xrpl.models.transactions import DIDSet
from xrpl.wallet import Wallet

from ..config import settings
from .client import Ledger, Submitted


def did_for(address: str) -> str:
    return f"did:xrpl:{settings().network_id.split(':')[1]}:{address}"


def publish(ledger: Ledger, wallet: Wallet, role: str, *, page_url: str | None = None) -> Submitted:
    # the on-ledger document is capped at 128 bytes, so it names the arm and points at the page for the rest
    document = {"id": did_for(wallet.address), "role": role}
    tx = DIDSet(
        account=wallet.address,
        did_document=json.dumps(document, separators=(",", ":")).encode().hex().upper(),
        uri=page_url.encode().hex().upper() if page_url else None,
    )
    return ledger.submit(tx, wallet)
