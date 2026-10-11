"""Permissioned domains: the rule that says which credentials admit an account to the cell's private vault."""
from __future__ import annotations

from xrpl.models.transactions import PermissionedDomainSet
from xrpl.models.transactions.permissioned_domain_set import Credential
from xrpl.wallet import Wallet

from .client import Ledger, Submitted
from .credentials import type_hex


def create(ledger: Ledger, owner: Wallet, accepted: list[tuple[str, str]]) -> tuple[Submitted, str]:
    """A domain admitting any account that holds one of the (issuer, credential kind) pairs. Returns its ID."""
    tx = PermissionedDomainSet(
        account=owner.address,
        accepted_credentials=[Credential(issuer=issuer, credential_type=type_hex(kind)) for issuer, kind in accepted],
    )
    done = ledger.submit(tx, owner)
    node = done.created("PermissionedDomain")
    if node is None:
        raise RuntimeError("the domain transaction succeeded but created no PermissionedDomain entry")
    return done, node["LedgerIndex"]


def find(ledger: Ledger, owner: str) -> str | None:
    for obj in ledger.objects(owner, "permissioned_domain"):
        return obj.get("index")
    return None
