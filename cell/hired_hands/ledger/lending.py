"""The loan desk: a broker attached to the vault lends XRP to the arms, who repay it from their earnings.
Every loan is signed by both the borrower and the broker before it exists."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from xrpl.models.transactions import LoanBrokerSet, LoanPay, LoanSet
from xrpl.transaction import autofill_and_sign, sign_loan_set_by_counterparty
from xrpl.wallet import Wallet

from .client import Ledger, Submitted

PERCENT = 1000   # rates are in tenths of a basis point: 1 % = 1000


@dataclass(frozen=True)
class Terms:
    principal_drops: int
    payments: int = 5
    interval_s: int = 3600
    grace_s: int = 600
    interest_rate_percent: float = 20.0   # annualised
    service_fee_drops: int = 1000


def set_broker(ledger: Ledger, owner: Wallet, vault_id: str, *, management_fee_percent: float = 1.0,
               data: str | None = None) -> tuple[Submitted, str]:
    tx = LoanBrokerSet(
        account=owner.address,
        vault_id=vault_id,
        management_fee_rate=int(management_fee_percent * PERCENT),
        data=data.encode().hex().upper() if data else None,
    )
    done = ledger.submit(tx, owner)
    node = done.created("LoanBroker")
    if node is None:
        raise RuntimeError("the broker transaction succeeded but created no LoanBroker entry")
    return done, node["LedgerIndex"]


def originate(ledger: Ledger, borrower: Wallet, broker_owner: Wallet, broker_id: str, terms: Terms) -> tuple[Submitted, str]:
    """The borrower asks, the broker countersigns, the vault pays out."""
    tx = LoanSet(
        account=borrower.address,
        loan_broker_id=broker_id,
        counterparty=broker_owner.address,
        principal_requested=str(terms.principal_drops),
        payment_total=terms.payments,
        payment_interval=terms.interval_s,
        grace_period=terms.grace_s,
        interest_rate=int(terms.interest_rate_percent * PERCENT),
        loan_service_fee=str(terms.service_fee_drops),
    )
    asked = autofill_and_sign(tx, ledger.client, borrower)
    agreed = sign_loan_set_by_counterparty(broker_owner, asked)
    done = ledger.submit_signed(agreed.tx_blob)
    node = done.created("Loan")
    if node is None:
        raise RuntimeError("the loan transaction succeeded but created no Loan entry")
    return done, node["LedgerIndex"]


def loans(ledger: Ledger, borrower: str) -> list[dict[str, Any]]:
    return [obj for obj in ledger.objects(borrower, "loan") if int(obj.get("PaymentRemaining", 0)) > 0]


def outstanding_drops(loan: dict[str, Any]) -> int:
    return int(math.ceil(float(loan.get("TotalValueOutstanding", "0"))))


def payment_due_drops(loan: dict[str, Any]) -> int:
    """One scheduled payment: the periodic amount plus the service fee, or everything left on the last one."""
    fee = int(loan.get("LoanServiceFee", "0"))
    if int(loan.get("PaymentRemaining", 0)) <= 1:
        return outstanding_drops(loan) + fee
    return int(math.ceil(float(loan["PeriodicPayment"]))) + fee


def payment(borrower: Wallet, loan_id: str, amount_drops: int) -> LoanPay:
    return LoanPay(account=borrower.address, loan_id=loan_id, amount=str(int(amount_drops)))


def pay(ledger: Ledger, borrower: Wallet, loan_id: str, amount_drops: int) -> Submitted:
    return ledger.submit(payment(borrower, loan_id, amount_drops), borrower)
