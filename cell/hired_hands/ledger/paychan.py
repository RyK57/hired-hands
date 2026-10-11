"""Payment channels: streaming pay for a human operator, signed off-ledger each second and claimed once."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xrpl.core.binarycodec import encode_for_signing_claim
from xrpl.core.keypairs import is_valid_message, sign
from xrpl.models.requests import AccountChannels
from xrpl.models.transactions import PaymentChannelClaim, PaymentChannelClaimFlag, PaymentChannelCreate
from xrpl.wallet import Wallet

from .client import Ledger, Submitted


@dataclass(frozen=True)
class Channel:
    id: str
    payer: str
    payee: str
    amount_drops: int
    public_key: str
    open_tx: str


@dataclass(frozen=True)
class Claim:
    channel: str
    amount_drops: int
    signature: str
    public_key: str


def open(ledger: Ledger, payer: Wallet, payee: str, amount_drops: int, *, settle_delay_s: int = 60) -> Channel:
    tx = PaymentChannelCreate(
        account=payer.address,
        destination=payee,
        amount=str(int(amount_drops)),
        settle_delay=settle_delay_s,
        public_key=payer.public_key,
    )
    done = ledger.submit(tx, payer)
    node = done.created("PayChannel")
    if node is None:
        raise RuntimeError("the channel transaction succeeded but created no PayChannel entry")
    return Channel(id=node["LedgerIndex"], payer=payer.address, payee=payee, amount_drops=int(amount_drops),
                   public_key=payer.public_key, open_tx=done.hash)


def authorize(payer: Wallet, channel: Channel, amount_drops: int) -> Claim:
    """The payer's off-ledger promise that `amount_drops` of the channel now belong to the payee."""
    message = bytes.fromhex(encode_for_signing_claim({"channel": channel.id, "amount": str(int(amount_drops))}))
    signature = sign(message, payer.private_key)
    return Claim(channel=channel.id, amount_drops=int(amount_drops), signature=signature.upper(),
                 public_key=payer.public_key)


def verify(claim: Claim) -> bool:
    message = bytes.fromhex(encode_for_signing_claim({"channel": claim.channel, "amount": str(claim.amount_drops)}))
    return is_valid_message(message, bytes.fromhex(claim.signature), claim.public_key)


def redeem(ledger: Ledger, payee: Wallet, claim: Claim, *, close: bool = True) -> Submitted:
    """The payee takes the latest claim on-ledger, closing the channel so the payer gets the rest back."""
    tx = PaymentChannelClaim(
        account=payee.address,
        channel=claim.channel,
        balance=str(claim.amount_drops),
        signature=claim.signature,
        public_key=claim.public_key,
        flags=PaymentChannelClaimFlag.TF_CLOSE if close else 0,
    )
    return ledger.submit(tx, payee)


def channels(ledger: Ledger, payer: str) -> list[dict[str, Any]]:
    return ledger.client.request(AccountChannels(account=payer)).result.get("channels", [])
