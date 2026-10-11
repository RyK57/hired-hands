"""The single-asset vault that pools XRP for the loan desk. It is closed-ended: depositors subscribe during a
window, the money is lent out during the investment period, and shares redeem after it."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from xrpl.models.currencies import XRP
from xrpl.models.requests import VaultInfo
from xrpl.models.transactions import VaultCreate, VaultCreateFlag, VaultDeposit, VaultWithdraw
from xrpl.models.transactions.vault_create import VaultKind
from xrpl.utils import datetime_to_ripple_time
from xrpl.wallet import Wallet

from .client import Ledger, Submitted


def ripple_time(seconds_from_now: float) -> int:
    return datetime_to_ripple_time(datetime.fromtimestamp(time.time() + seconds_from_now, tz=timezone.utc))


def create(ledger: Ledger, owner: Wallet, *, subscription_s: float, redemption_s: float,
           domain_id: str | None = None, data: str | None = None) -> tuple[Submitted, str]:
    """A private XRP vault open for deposits for `subscription_s` seconds and lending until `redemption_s`.
    With a domain, only credentialed accounts may deposit; the owner always may."""
    tx = VaultCreate(
        account=owner.address,
        asset=XRP(),
        vault_kind=VaultKind.CLOSED,
        subscription_date=ripple_time(subscription_s),
        redemption_date=ripple_time(redemption_s),
        flags=VaultCreateFlag.TF_VAULT_PRIVATE if domain_id else 0,
        domain_id=domain_id,
        data=data.encode().hex().upper() if data else None,
    )
    done = ledger.submit(tx, owner)
    node = done.created("Vault")
    if node is None:
        raise RuntimeError("the vault transaction succeeded but created no Vault entry")
    return done, node["LedgerIndex"]


def info(ledger: Ledger, vault_id: str) -> dict[str, Any]:
    return ledger.client.request(VaultInfo(vault_id=vault_id)).result.get("vault", {})


def deposit(ledger: Ledger, depositor: Wallet, vault_id: str, amount_drops: int) -> Submitted:
    return ledger.submit(VaultDeposit(account=depositor.address, vault_id=vault_id, amount=str(int(amount_drops))),
                         depositor)


def withdraw(ledger: Ledger, holder: Wallet, vault_id: str, amount_drops: int) -> Submitted:
    return ledger.submit(VaultWithdraw(account=holder.address, vault_id=vault_id, amount=str(int(amount_drops))),
                         holder)


def shares_held(ledger: Ledger, holder: str, share_mpt_id: str) -> int:
    for obj in ledger.objects(holder, "mptoken"):
        if obj.get("MPTokenIssuanceID") == share_mpt_id:
            return int(obj.get("MPTAmount", "0"))
    return 0
