"""On-ledger credentials: short-lived attestations the operator issues to arms and to vault depositors."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from xrpl.models.transactions import CredentialAccept, CredentialCreate, CredentialDelete
from xrpl.utils import datetime_to_ripple_time, ripple_time_to_posix
from xrpl.wallet import Wallet

from .client import Ledger, Submitted

HEALTH = "robot-health"          # renewed from live servo telemetry; gates bidding and borrowing
DEPOSITOR = "verified-depositor"  # gates the private vault

LSF_ACCEPTED = 0x00010000


def type_hex(kind: str) -> str:
    return kind.encode().hex().upper()


def issue(ledger: Ledger, issuer: Wallet, subject: str, kind: str, *, expires_in_s: float | None = None,
          uri: str | None = None) -> Submitted:
    expiration = None
    if expires_in_s is not None:
        expiration = datetime_to_ripple_time(
            datetime.fromtimestamp(time.time() + expires_in_s, tz=timezone.utc))
    tx = CredentialCreate(
        account=issuer.address,
        subject=subject,
        credential_type=type_hex(kind),
        expiration=expiration,
        uri=uri.encode().hex().upper() if uri else None,
    )
    return ledger.submit(tx, issuer)


def accept(ledger: Ledger, subject: Wallet, issuer: str, kind: str) -> Submitted:
    tx = CredentialAccept(account=subject.address, issuer=issuer, credential_type=type_hex(kind))
    return ledger.submit(tx, subject)


def revoke(ledger: Ledger, issuer: Wallet, subject: str, kind: str) -> Submitted:
    tx = CredentialDelete(account=issuer.address, subject=subject, credential_type=type_hex(kind))
    return ledger.submit(tx, issuer)


def find(ledger: Ledger, subject: str, issuer: str, kind: str) -> dict[str, Any] | None:
    """The credential ledger object, or None when the subject does not hold one from this issuer."""
    for obj in ledger.objects(subject, "credential"):
        if obj.get("Issuer") == issuer and obj.get("CredentialType") == type_hex(kind):
            return obj
    return None


def status(obj: dict[str, Any] | None) -> str:
    """'valid', 'pending' (issued, not yet accepted), 'expired' or 'none'."""
    if obj is None:
        return "none"
    expiration = obj.get("Expiration")
    if expiration is not None and ripple_time_to_posix(int(expiration)) < time.time():
        return "expired"
    return "valid" if int(obj.get("Flags", 0)) & LSF_ACCEPTED else "pending"
