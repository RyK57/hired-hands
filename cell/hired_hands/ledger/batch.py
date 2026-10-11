"""Atomic settlement: every transfer a job produces lands in one all-or-nothing batch, or none does.
Transactions from several accounts ride in the same batch; each of those accounts co-signs it."""
from __future__ import annotations

from dataclasses import replace

from xrpl.models.transactions import Batch, BatchFlag, Payment, Transaction
from xrpl.transaction import autofill, sign, sign_multiaccount_batch
from xrpl.wallet import Wallet

from .client import Ledger, Submitted

BASE_FEE_DROPS = 10


def payment(sender: Wallet, destination: str, amount_drops: int) -> Payment:
    return Payment(account=sender.address, destination=destination, amount=str(int(amount_drops)))


def settle(ledger: Ledger, submitter: Wallet, transactions: list[Transaction], cosigners: list[Wallet]) -> Submitted:
    """Submit `transactions` as one batch. `cosigners` are the wallets of every inner account other than
    the submitter's; the submitter signs the batch as a whole."""
    batch = Batch(account=submitter.address, raw_transactions=transactions, flags=BatchFlag.TF_ALL_OR_NOTHING)
    filled = autofill(batch, ledger.client)
    # the outer fee covers the batch itself, every inner transaction and every co-signature
    filled = replace(filled, fee=str(BASE_FEE_DROPS * (4 + len(transactions) + len(cosigners)) * 2))
    seen: set[str] = set()
    for wallet in cosigners:
        if wallet.address == submitter.address or wallet.address in seen:
            continue
        filled = sign_multiaccount_batch(wallet, filled)
        seen.add(wallet.address)
    return ledger.submit_signed(sign(filled, submitter))
