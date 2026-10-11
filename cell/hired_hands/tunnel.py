"""A public address for the job API, so hirers anywhere can reach a cell that sits behind a home router."""
from __future__ import annotations

import shutil
import subprocess
import time

import httpx

NGROK_API = "http://127.0.0.1:4040/api/tunnels"


class Tunnel:
    def __init__(self, port: int):
        self.port = port
        self.url: str | None = None
        self._process: subprocess.Popen | None = None

    def open(self, timeout_s: float = 15.0) -> str:
        if shutil.which("ngrok") is None:
            raise RuntimeError("ngrok is not installed; set HANDS_PUBLIC_URL to an address you expose yourself")
        self._process = subprocess.Popen(
            ["ngrok", "http", str(self.port), "--log=stdout", "--log-format=json"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                tunnels = httpx.get(NGROK_API, timeout=2).json().get("tunnels", [])
                for tunnel in tunnels:
                    if tunnel.get("public_url", "").startswith("https://"):
                        self.url = tunnel["public_url"]
                        return self.url
            except Exception:
                pass
            time.sleep(0.5)
        self.close()
        raise RuntimeError("the tunnel did not come up in time")

    def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self.url = None
