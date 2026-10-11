"""Conditional escrows: a job's payment is locked on-ledger and can only be released by whoever holds the
secret behind the escrow's condition. The cell gives that secret to the arm that watches the work."""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from xrpl.models.transactions import EscrowCancel, EscrowCreate, EscrowFinish
from xrpl.utils import datetime_to_ripple_time
from xrpl.wallet import Wallet

from .client import Ledger, Submitted

# PREIMAGE-SHA-256 crypto-conditions (RFC draft), DER-encoded by hand: the only kind the ledger accepts.
_CONDITION_PREFIX = "A0258020"   # type 0, 32-byte fingerprint follows
_CONDITION_SUFFIX = "810120"     # cost = 32 (the preimage length)
_FULFILLMENT_PREFIX = "A0228020"  # 32-byte preimage follows
FINISH_FEE_DROPS = "400"          # base fee x (33 + fulfillment bytes / 16), rounded up


def new_secret() -> bytes:
    return os.urandom(32)


def condition(secret: bytes) -> str:
    return _CONDITION_PREFIX + hashlib.sha256(secret).hexdigest().upper() + _CONDITION_SUFFIX


def fulfillment(secret: bytes) -> str:
    return _FULFILLMENT_PREFIX + secret.hex().upper()


def _ripple_time(seconds_from_now: float) -> int:
    from datetime import datetime, timezone
    return datetime_to_ripple_time(datetime.fromtimestamp(time.time() + seconds_from_now, tz=timezone.utc))


@dataclass(frozen=True)
class Escrow:
    owner: str
    destination: str
    sequence: int
    amount_drops: int
    condition: str
    tx_hash: str


def lock(ledger: Ledger, owner: Wallet, destination: str, amount_drops: int, secret: bytes,
         *, cancel_after_s: float = 3600) -> Escrow:
    """Lock `amount_drops` for `destination` behind the condition of `secret`."""
    tx = EscrowCreate(
        account=owner.address,
        destination=destination,
        amount=str(int(amount_drops)),
        condition=condition(secret),
        cancel_after=_ripple_time(cancel_after_s),
    )
    done = ledger.submit(tx, owner)
    return Escrow(owner=owner.address, destination=destination, sequence=int(done.tx["Sequence"]),
                  amount_drops=int(amount_drops), condition=condition(secret), tx_hash=done.hash)


def release(ledger: Ledger, finisher: Wallet, escrow: Escrow, secret: bytes) -> Submitted:
    """Anyone holding the secret can finish the escrow; the funds go to its destination."""
    tx = EscrowFinish(
        account=finisher.address,
        owner=escrow.owner,
        offer_sequence=escrow.sequence,
        condition=escrow.condition,
        fulfillment=fulfillment(secret),
        fee=FINISH_FEE_DROPS,
    )
    return ledger.submit(tx, finisher)


def cancel(ledger: Ledger, canceller: Wallet, escrow: Escrow) -> Submitted:
    """After CancelAfter the funds can be returned to the owner by anyone."""
    tx = EscrowCancel(account=canceller.address, owner=escrow.owner, offer_sequence=escrow.sequence)
    return ledger.submit(tx, canceller)
