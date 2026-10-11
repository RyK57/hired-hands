"""The cell's finances: a vault that verified depositors fund, a loan desk the arms borrow from, and the
repayments that come out of every job."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from xrpl.models.transactions import LoanPay
from xrpl.utils import ripple_time_to_posix

from .config import settings
from .events import Publisher
from .ledger import credentials, domain, lending, vault
from .ledger.client import Ledger

Log = Callable[[str], None]


@dataclass(frozen=True)
class Repayment:
    loan_id: str
    amount_drops: int
    transaction: LoanPay


class Desk:
    def __init__(self, ledger: Ledger, publisher: Publisher | None = None):
        self.ledger = ledger
        self.publisher = publisher or Publisher()
        self.path = settings().state_dir / "finance.json"
        self.state: dict[str, Any] = json.loads(self.path.read_text()) if self.path.exists() else {}

    @property
    def ready(self) -> bool:
        return bool(self.state.get("vault_id") and self.state.get("broker_id"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2) + "\n")

    # -- setting up ---------------------------------------------------------------------------------

    def setup(self, *, seed_drops: int, subscription_s: float = 180, redemption_days: float = 7,
              log: Log = print) -> None:
        """Open the vault: a domain only verified depositors can enter, the vault behind it, the broker on it,
        and the operator's own seed deposit. Deposits stay open for `subscription_s` seconds."""
        operator, broker = self.ledger.wallet("operator"), self.ledger.wallet("broker")
        done, domain_id = domain.create(self.ledger, broker, [(operator.address, credentials.DEPOSITOR)])
        log(f"domain {domain_id[:12]}… admits holders of the operator's '{credentials.DEPOSITOR}' credential")
        done, vault_id = vault.create(self.ledger, broker, subscription_s=subscription_s,
                                      redemption_s=redemption_days * 86400, domain_id=domain_id,
                                      data="Hired Hands working capital")
        opens_until = time.time() + subscription_s
        log(f"vault {vault_id[:12]}… created ({done.hash[:12]}); deposits open for {subscription_s:.0f} s")
        seed = vault.deposit(self.ledger, broker, vault_id, seed_drops)
        log(f"seeded with {seed_drops / 1e6:.0f} XRP ({seed.hash[:12]})")
        done, broker_id = lending.set_broker(self.ledger, broker, vault_id, management_fee_percent=1.0,
                                             data="Hired Hands loan desk")
        log(f"loan desk {broker_id[:12]}… open ({done.hash[:12]})")
        info = vault.info(self.ledger, vault_id)
        self.state = {
            "domain_id": domain_id, "vault_id": vault_id, "broker_id": broker_id,
            "share_mpt_id": info.get("ShareMPTID"), "subscription_until": opens_until,
            "redemption_at": time.time() + redemption_days * 86400,
        }
        self._save()
        self.publisher.cell(vault_id=vault_id, domain_id=domain_id, broker_address=broker.address)
        self.publisher.event("vault.deposit", f"the operator seeded the vault with {seed_drops / 1e6:.0f} XRP",
                             tx_hash=seed.hash, amount_drops=seed_drops)

    def admit(self, address: str, *, name: str | None, company_domain: str | None, log: Log = print) -> str:
        """Issue the depositor credential to an account that passed verification."""
        operator = self.ledger.wallet("operator")
        held = credentials.find(self.ledger, address, operator.address, credentials.DEPOSITOR)
        if credentials.status(held) == "valid":
            log(f"{address} already holds the depositor credential")
            return ""
        if held is not None:
            credentials.revoke(self.ledger, operator, address, credentials.DEPOSITOR)
        done = credentials.issue(self.ledger, operator, address, credentials.DEPOSITOR, expires_in_s=30 * 86400)
        log(f"depositor credential issued to {address} ({done.hash[:12]})")
        self.publisher.depositor(address, name=name, domain=company_domain, verified=True, credential_tx=done.hash)
        self.publisher.event("credential.issued", f"{name or address} admitted as a depositor", tx_hash=done.hash)
        return done.hash

    def deposit(self, depositor_name: str, amount_drops: int, log: Log = print) -> str:
        wallet = self.ledger.wallet(depositor_name)
        operator = self.ledger.wallet("operator")
        held = credentials.find(self.ledger, wallet.address, operator.address, credentials.DEPOSITOR)
        if credentials.status(held) == "pending":
            credentials.accept(self.ledger, wallet, operator.address, credentials.DEPOSITOR)
        done = vault.deposit(self.ledger, wallet, self.state["vault_id"], amount_drops)
        log(f"{wallet.address} deposited {amount_drops / 1e6:.2f} XRP ({done.hash[:12]})")
        shares = vault.shares_held(self.ledger, wallet.address, self.state.get("share_mpt_id", ""))
        self.publisher.depositor(wallet.address, deposited_drops=amount_drops, shares=str(shares), deposit_tx=done.hash)
        self.publisher.event("vault.deposit", f"{amount_drops / 1e6:.2f} XRP deposited into the vault",
                             tx_hash=done.hash, amount_drops=amount_drops)
        return done.hash

    # -- lending ------------------------------------------------------------------------------------

    def lend(self, role: str, principal_drops: int, *, log: Log = print, **terms: Any) -> str:
        opens = float(self.state.get("subscription_until", 0))
        if time.time() < opens + 5:
            wait = opens + 5 - time.time()
            log(f"deposits are still open; lending starts in {wait:.0f} s")
            time.sleep(wait)
        borrower, broker = self.ledger.wallet(role), self.ledger.wallet("broker")
        done, loan_id = lending.originate(self.ledger, borrower, broker, self.state["broker_id"],
                                          lending.Terms(principal_drops=principal_drops, **terms))
        loan = next((l for l in lending.loans(self.ledger, borrower.address) if l.get("index") == loan_id), None)
        outstanding = lending.outstanding_drops(loan) if loan else principal_drops
        log(f"{role} borrowed {principal_drops / 1e6:.2f} XRP ({done.hash[:12]}); owes {outstanding / 1e6:.3f} XRP")
        self.publisher.loan(loan_id, arm_role=role, principal_drops=principal_drops, outstanding_drops=outstanding,
                            interest_bps=int(lending.Terms(principal_drops=0, **terms).interest_rate_percent * 100),
                            status="active", open_tx=done.hash)
        self.publisher.arm(role, debt_drops=self.outstanding(role))
        self.publisher.event("loan.opened", f"{role} took a {principal_drops / 1e6:.2f} XRP loan from the desk, "
                             "co-signed by the broker", arm_role=role, tx_hash=done.hash, amount_drops=principal_drops)
        return loan_id

    def outstanding(self, role: str) -> int:
        return sum(lending.outstanding_drops(l) for l in lending.loans(self.ledger, self.ledger.address(role)))

    def repayment(self, role: str, earned_drops: int) -> Repayment | None:
        """The next scheduled payment on the arm's oldest loan, to ride in the job's settlement batch."""
        active = lending.loans(self.ledger, self.ledger.address(role))
        if not active:
            return None
        loan = min(active, key=lambda l: int(l.get("LoanSequence", 0)))
        amount = lending.payment_due_drops(loan)
        return Repayment(loan_id=loan["index"], amount_drops=amount,
                         transaction=lending.payment(self.ledger.wallet(role), loan["index"], amount))

    def record_payment(self, job_id: str, role: str, repayment: Repayment, tx_hash: str) -> None:
        remaining = next((l for l in lending.loans(self.ledger, self.ledger.address(role))
                          if l.get("index") == repayment.loan_id), None)
        outstanding = lending.outstanding_drops(remaining) if remaining else 0
        self.publisher.loan(repayment.loan_id, outstanding_drops=outstanding, last_payment_tx=tx_hash,
                            status="active" if remaining else "repaid",
                            closed_at=None if remaining else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self.publisher.arm(role, debt_drops=self.outstanding(role))
        self.publisher.event("loan.payment", f"{role} repaid {repayment.amount_drops / 1e6:.3f} XRP"
                             + (f"; {outstanding / 1e6:.3f} XRP left" if remaining else "; loan repaid in full"),
                             job_id=job_id, arm_role=role, tx_hash=tx_hash, amount_drops=repayment.amount_drops)

    def sync(self) -> None:
        """Publish the vault, every loan and every depositor as they stand on the ledger."""
        if not self.ready:
            return
        broker = self.ledger.address("broker")
        self.publisher.cell(vault_id=self.state["vault_id"], domain_id=self.state.get("domain_id"), broker_address=broker)
        for role in ("left", "head", "right"):
            if not self.ledger.has_wallet(role):
                continue
            debt = 0
            for loan in lending.loans(self.ledger, self.ledger.address(role)):
                outstanding = lending.outstanding_drops(loan)
                debt += outstanding
                self.publisher.loan(loan["index"], arm_role=role, principal_drops=int(loan.get("PrincipalOutstanding", 0)),
                                    outstanding_drops=outstanding, interest_bps=int(loan.get("InterestRate", 0)) // 10,
                                    status="active")
            self.publisher.arm(role, debt_drops=debt)
        share_id = self.state.get("share_mpt_id", "")
        for name in ("depositor", "broker"):
            if not self.ledger.has_wallet(name):
                continue
            address = self.ledger.address(name)
            shares = vault.shares_held(self.ledger, address, share_id) if share_id else 0
            if shares:
                self.publisher.depositor(address, name="Hired Hands operator" if name == "broker" else None,
                                         verified=True, deposited_drops=shares, shares=str(shares))

    # -- reporting ----------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        if not self.ready:
            return {"ready": False}
        info = vault.info(self.ledger, self.state["vault_id"])
        out: dict[str, Any] = {
            "ready": True,
            "vault_id": self.state["vault_id"], "broker_id": self.state["broker_id"],
            "assets_total_drops": int(info.get("AssetsTotal", 0)), "assets_available_drops": int(info.get("AssetsAvailable", 0)),
            "shares_outstanding": info.get("shares", {}).get("OutstandingAmount"),
            "deposits_open_until": self.state.get("subscription_until"),
            "redemption_at": self.state.get("redemption_at"),
            "loans": {},
        }
        for role in ("left", "head", "right"):
            if self.ledger.has_wallet(role):
                for loan in lending.loans(self.ledger, self.ledger.address(role)):
                    out["loans"][loan["index"]] = {
                        "borrower": role, "outstanding_drops": lending.outstanding_drops(loan),
                        "payments_remaining": int(loan.get("PaymentRemaining", 0)),
                        "next_due": ripple_time_to_posix(int(loan["NextPaymentDueDate"])) if loan.get("NextPaymentDueDate") else None,
                    }
        return out
