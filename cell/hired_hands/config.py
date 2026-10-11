"""Runtime settings, read once from the environment (and cell/.env when present)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CELL_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = CELL_DIR / ".env"

NETWORKS: dict[str, dict[str, str]] = {
    "devnet": {
        "id": "xrpl:2",
        "rpc": "https://s.devnet.rippletest.net:51234",
        "ws": "wss://s.devnet.rippletest.net:51233",
        "explorer": "https://devnet.xrpl.org",
    },
    "testnet": {
        "id": "xrpl:1",
        "rpc": "https://s.altnet.rippletest.net:51234",
        "ws": "wss://s.altnet.rippletest.net:51233",
        "explorer": "https://testnet.xrpl.org",
    },
}


def _load_env_file(path: Path) -> None:
    """Export KEY=VALUE lines from a .env file without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    network: str
    network_id: str
    rpc_url: str
    ws_url: str
    explorer_url: str
    state_dir: Path
    captures_dir: Path
    rig_file: Path
    urdf_path: Path
    camera_index: int
    api_host: str
    api_port: int
    public_url: str | None
    dashboard_url: str | None
    supabase_url: str | None
    supabase_key: str | None
    anthropic_api_key: str | None
    anthropic_model: str
    context_dev_api_key: str | None
    elevenlabs_api_key: str | None

    def explorer_tx(self, tx_hash: str) -> str:
        return f"{self.explorer_url}/transactions/{tx_hash}"

    def explorer_account(self, address: str) -> str:
        return f"{self.explorer_url}/accounts/{address}"


@lru_cache(maxsize=1)
def settings() -> Settings:
    _load_env_file(ENV_FILE)
    env = os.environ.get
    network = env("HANDS_NETWORK", "devnet")
    if network not in NETWORKS:
        raise ValueError(f"HANDS_NETWORK must be one of {sorted(NETWORKS)}, got {network!r}")
    net = NETWORKS[network]
    state_dir = Path(env("HANDS_STATE_DIR", CELL_DIR / "state")).expanduser()
    return Settings(
        network=network,
        network_id=net["id"],
        rpc_url=env("HANDS_RPC_URL", net["rpc"]),
        ws_url=env("HANDS_WS_URL", net["ws"]),
        explorer_url=env("HANDS_EXPLORER_URL", net["explorer"]),
        state_dir=state_dir,
        captures_dir=Path(env("HANDS_CAPTURES_DIR", CELL_DIR / "captures")).expanduser(),
        rig_file=Path(env("HANDS_RIG_FILE", CELL_DIR / "rig.json")).expanduser(),
        urdf_path=Path(env("HANDS_URDF", CELL_DIR / "models" / "so101.urdf")).expanduser(),
        camera_index=int(env("HANDS_CAMERA_INDEX", "0")),
        api_host=env("HANDS_API_HOST", "0.0.0.0"),
        api_port=int(env("HANDS_API_PORT", "8402")),
        public_url=env("HANDS_PUBLIC_URL") or None,
        dashboard_url=env("HANDS_DASHBOARD_URL") or None,
        supabase_url=env("HANDS_SUPABASE_URL") or None,
        supabase_key=env("HANDS_SUPABASE_KEY") or None,
        anthropic_api_key=env("ANTHROPIC_API_KEY") or None,
        anthropic_model=env("HANDS_ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        context_dev_api_key=env("CONTEXT_DEV_API_KEY") or None,
        elevenlabs_api_key=env("ELEVENLABS_API_KEY") or None,
    )
