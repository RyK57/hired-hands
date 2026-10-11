"""The cell's accounts on Base, where it is paid in AUSD."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .config import settings

NETWORK = "eip155:84532"                       # Base Sepolia
RPC_URL = "https://sepolia.base.org"
EXPLORER_TX = "https://sepolia.basescan.org/tx/"
AUSD = {
    "address": "0xa9012a055bd4e0eDfF8Ce09f960291C09D5322dC",
    "symbol": "AUSD",
    "decimals": 6,
    "name": "Agora Dollar",   # the EIP-712 domain name the token signs under
    "version": "1",
}
FACILITATOR_URL = "https://x402.org/facilitator"

ACCOUNTS = ("treasury", "client")


def to_atomic(amount: float) -> str:
    return str(int(round(amount * 10 ** AUSD["decimals"])))


def from_atomic(amount: str | int) -> float:
    return int(amount) / 10 ** AUSD["decimals"]


class Wallets:
    """Named Base accounts, created on first use and kept beside the XRPL wallets."""

    def __init__(self, state_dir: Path | None = None):
        self.path = (state_dir or settings().state_dir) / "evm.json"
        self._keys: dict[str, str] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def has(self, name: str) -> bool:
        return name in self._keys

    def account(self, name: str) -> LocalAccount:
        if name not in self._keys:
            self._keys[name] = Account.create().key.hex()
            self._save()
        return Account.from_key(self._keys[name])

    def import_key(self, name: str, private_key: str) -> LocalAccount:
        account = Account.from_key(private_key)
        self._keys[name] = account.key.hex()
        self._save()
        return account

    def address(self, name: str) -> str:
        return self.account(name).address

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._keys, indent=2) + "\n")
        os.chmod(self.path, 0o600)


def _call(to: str, data: str) -> str:
    response = httpx.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                         "params": [{"to": to, "data": data}, "latest"]}, timeout=20)
    return response.json().get("result", "0x0")


def ausd_balance(address: str) -> float:
    """AUSD held by `address`, in whole dollars."""
    selector = "0x70a08231"  # balanceOf(address)
    data = selector + address.lower().replace("0x", "").rjust(64, "0")
    return from_atomic(int(_call(AUSD["address"], data), 16))


def explorer_tx(tx_hash: str) -> str:
    return EXPLORER_TX + tx_hash


def facilitator_supports(network: str = NETWORK) -> dict[str, Any] | None:
    try:
        kinds = httpx.get(f"{FACILITATOR_URL}/supported", timeout=15).json().get("kinds", [])
    except Exception:
        return None
    return next((k for k in kinds if k.get("network") == network and k.get("scheme") == "exact"
                 and k.get("x402Version") == 2), None)


def refund(to: str, amount_atomic: str) -> str:
    """Send AUSD back from the treasury: a plain ERC-20 transfer the treasury pays gas for."""
    from eth_account import Account as _Account

    treasury = Wallets().account("treasury")
    selector = "0xa9059cbb"  # transfer(address,uint256)
    data = selector + to.lower().replace("0x", "").rjust(64, "0") + format(int(amount_atomic), "x").rjust(64, "0")

    def rpc(method: str, params: list) -> Any:
        out = httpx.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30).json()
        if "error" in out:
            raise RuntimeError(out["error"].get("message", "rpc error"))
        return out["result"]

    nonce = int(rpc("eth_getTransactionCount", [treasury.address, "pending"]), 16)
    gas_price = int(rpc("eth_gasPrice", []), 16)
    tx = {"to": AUSD["address"], "data": data, "value": 0, "nonce": nonce, "gas": 90_000,
          "gasPrice": int(gas_price * 1.2), "chainId": int(NETWORK.split(":")[1])}
    signed = _Account.sign_transaction(tx, treasury.key)
    return rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex().removeprefix("0x")])


def transfer_authorization(account: LocalAccount, requirements: dict[str, Any]) -> dict[str, Any]:
    """Sign a gasless AUSD transfer (EIP-3009) that pays `requirements`; the facilitator submits it."""
    import secrets
    import time

    from eth_account import Account as _Account

    now = int(time.time())
    authorization = {
        "from": account.address,
        "to": requirements["payTo"],
        "value": str(requirements["amount"]),
        "validAfter": str(now - 60),
        "validBefore": str(now + int(requirements.get("maxTimeoutSeconds", 600))),
        "nonce": "0x" + secrets.token_hex(32),
    }
    extra = requirements.get("extra") or {}
    domain = {
        "name": extra.get("name", AUSD["name"]),
        "version": extra.get("version", AUSD["version"]),
        "chainId": int(str(requirements["network"]).split(":")[1]),
        "verifyingContract": requirements["asset"],
    }
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
        ]
    }
    message = {**authorization, "value": int(authorization["value"]), "validAfter": int(authorization["validAfter"]),
               "validBefore": int(authorization["validBefore"]), "nonce": bytes.fromhex(authorization["nonce"][2:])}
    signed = _Account.sign_typed_data(account.key, domain, types, message)
    return {"signature": "0x" + signed.signature.hex().removeprefix("0x"), "authorization": authorization}
