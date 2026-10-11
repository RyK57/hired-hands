"""Connection to the XRP Ledger, the cell's wallets, and the one path every transaction takes."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, AccountObjects, ServerInfo
from xrpl.models.transactions import Transaction
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

from ..config import settings

# Every party the cell transacts as. Arms are their own economic agents; the rest are the business around them.
WALLETS = (
    "operator",      # issues credentials, runs the API, takes the protocol fee
    "treasury",      # holds escrowed job payments and settles each job
    "broker",        # owns the vault and the loan desk the arms borrow from
    "left", "head", "right",
    "client",        # the default hirer used by the command line
    "teleoperator",  # the human who takes over when autonomy fails
    "depositor",     # a vault depositor
)


class LedgerError(RuntimeError):
    def __init__(self, result: str, tx: dict[str, Any] | None = None):
        super().__init__(result)
        self.result = result
        self.tx = tx or {}


@dataclass(frozen=True)
class Submitted:
    hash: str
    result: str
    validated: bool
    tx: dict[str, Any]
    meta: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.result == "tesSUCCESS"

    @property
    def explorer(self) -> str:
        return settings().explorer_tx(self.hash)

    def created(self, ledger_entry_type: str) -> dict[str, Any] | None:
        """The first ledger object of this type the transaction created, from its metadata."""
        for node in self.meta.get("AffectedNodes", []):
            created = node.get("CreatedNode")
            if created and created.get("LedgerEntryType") == ledger_entry_type:
                return created
        return None


class Ledger:
    def __init__(self, rpc_url: str | None = None, state_dir: Path | None = None):
        self.rpc_url = rpc_url or settings().rpc_url
        self.client = JsonRpcClient(self.rpc_url)
        self.wallet_file = (state_dir or settings().state_dir) / "wallets.json"
        self._seeds: dict[str, str] = {}
        if self.wallet_file.exists():
            self._seeds = json.loads(self.wallet_file.read_text())

    # -- wallets -------------------------------------------------------------------------------------

    def has_wallet(self, name: str) -> bool:
        return name in self._seeds

    def wallet(self, name: str) -> Wallet:
        """The named wallet, created and funded from the faucet the first time it is asked for."""
        if name not in self._seeds:
            wallet = generate_faucet_wallet(self.client, debug=False)
            self._seeds[name] = wallet.seed
            self._save()
            return wallet
        return Wallet.from_seed(self._seeds[name])

    def address(self, name: str) -> str:
        return self.wallet(name).address

    def top_up(self, name: str) -> None:
        """Ask the faucet for more XRP for an existing wallet."""
        generate_faucet_wallet(self.client, wallet=self.wallet(name), debug=False)

    def _save(self) -> None:
        self.wallet_file.parent.mkdir(parents=True, exist_ok=True)
        self.wallet_file.write_text(json.dumps(self._seeds, indent=2) + "\n")
        os.chmod(self.wallet_file, 0o600)

    # -- reads -------------------------------------------------------------------------------------

    def account(self, address: str) -> dict[str, Any]:
        return self.client.request(AccountInfo(account=address, ledger_index="validated")).result["account_data"]

    def balance(self, address: str) -> int:
        """Spendable drops, zero for an account that does not exist yet."""
        try:
            return int(self.account(address)["Balance"])
        except Exception:
            return 0

    def objects(self, address: str, kind: str | None = None) -> list[dict[str, Any]]:
        request = AccountObjects(account=address, ledger_index="validated", type=kind) if kind else \
            AccountObjects(account=address, ledger_index="validated")
        return self.client.request(request).result.get("account_objects", [])

    def network_id(self) -> int | None:
        info = self.client.request(ServerInfo()).result.get("info", {})
        return info.get("network_id")

    # -- writes ------------------------------------------------------------------------------------

    def submit(self, tx: Transaction, wallet: Wallet, *, expect_success: bool = True) -> Submitted:
        """Autofill, sign, submit and wait for validation."""
        response = submit_and_wait(tx, self.client, wallet, autofill=True)
        return self._submitted(response.result, expect_success)

    def submit_signed(self, tx_or_blob: Transaction | str, *, expect_success: bool = True) -> Submitted:
        """Submit something already signed (a presigned payment, a co-signed loan, a multi-account batch)."""
        response = submit_and_wait(tx_or_blob, self.client)
        return self._submitted(response.result, expect_success)

    @staticmethod
    def _submitted(result: dict[str, Any], expect_success: bool) -> Submitted:
        tx = result.get("tx_json", result)
        meta = result.get("meta", {})
        engine = meta.get("TransactionResult", result.get("engine_result", "unknown"))
        submitted = Submitted(
            hash=result.get("hash", tx.get("hash", "")),
            result=engine,
            validated=bool(result.get("validated")),
            tx=tx,
            meta=meta,
        )
        if expect_success and not submitted.ok:
            raise LedgerError(engine, tx)
        return submitted
