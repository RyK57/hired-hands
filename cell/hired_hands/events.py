"""Everything the cell does is published as it happens, so the dashboard shows it live."""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)


class Publisher:
    """Writes to the database from a background thread; the control loop never waits on the network.
    Without a configured database every call is a no-op."""

    def __init__(self) -> None:
        cfg = settings()
        self._client = None
        if cfg.supabase_url and cfg.supabase_key:
            from supabase import create_client
            self._client = create_client(cfg.supabase_url, cfg.supabase_key)
        self._queue: queue.Queue[tuple[str, tuple, dict]] = queue.Queue()
        self._thread = threading.Thread(target=self._drain, name="publisher", daemon=True)
        self._thread.start()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # -- queueing ---------------------------------------------------------------------------------

    def _enqueue(self, op: str, *args: Any, **kwargs: Any) -> None:
        if self._client is not None:
            self._queue.put((op, args, kwargs))

    def _drain(self) -> None:
        while True:
            op, args, kwargs = self._queue.get()
            try:
                getattr(self, f"_do_{op}")(*args, **kwargs)
            except Exception as exc:  # the dashboard is a window, never a reason to stop the arms
                log.warning("publish %s failed: %s", op, exc)

    def flush(self, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while not self._queue.empty() and time.time() < deadline:
            time.sleep(0.05)

    # -- public api -------------------------------------------------------------------------------

    def cell(self, **fields: Any) -> None:
        self._enqueue("upsert", "cell", {"id": "cell", **fields})

    def arm(self, role: str, **fields: Any) -> None:
        self._enqueue("upsert", "arms", {"role": role, **fields})

    def job(self, job_id: str, **fields: Any) -> None:
        self._enqueue("upsert", "jobs", {"id": job_id, **fields})

    def bid(self, job_id: str, **fields: Any) -> None:
        self._enqueue("insert", "bids", {"job_id": job_id, **fields})

    def channel(self, channel_id: str, **fields: Any) -> None:
        self._enqueue("upsert", "channels", {"id": channel_id, **fields})

    def loan(self, loan_id: str, **fields: Any) -> None:
        self._enqueue("upsert", "loans", {"id": loan_id, **fields})

    def depositor(self, address: str, **fields: Any) -> None:
        self._enqueue("upsert", "depositors", {"address": address, **fields})

    def event(self, kind: str, message: str, *, job_id: str | None = None, arm_role: str | None = None,
              tx_hash: str | None = None, amount_drops: int | None = None, meta: dict | None = None) -> None:
        row: dict[str, Any] = {"kind": kind, "message": message}
        if job_id:
            row["job_id"] = job_id
        if arm_role:
            row["arm_role"] = arm_role
        if tx_hash:
            row["tx_hash"] = tx_hash
            row["explorer_url"] = settings().explorer_tx(tx_hash)
        if amount_drops is not None:
            row["amount_drops"] = int(amount_drops)
        if meta:
            row["meta"] = meta
        log.info("%s %s%s", kind, message, f" ({tx_hash[:8]})" if tx_hash else "")
        self._enqueue("insert", "events", row)

    def upload(self, path: Path, key: str) -> str | None:
        """Store an image and return its public URL (synchronously: the caller needs the URL)."""
        if self._client is None:
            return None
        try:
            bucket = self._client.storage.from_("captures")
            bucket.upload(key, path.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"})
            return bucket.get_public_url(key)
        except Exception as exc:
            log.warning("upload %s failed: %s", key, exc)
            return None

    # -- workers ----------------------------------------------------------------------------------

    def _do_upsert(self, table: str, row: dict[str, Any]) -> None:
        assert self._client is not None
        self._client.table(table).upsert(row).execute()

    def _do_insert(self, table: str, row: dict[str, Any]) -> None:
        assert self._client is not None
        self._client.table(table).insert(row).execute()
