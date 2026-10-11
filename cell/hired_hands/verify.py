"""Who is asking to deposit? A company is looked up by its website before it is admitted to the vault."""
from __future__ import annotations

from typing import Any

import httpx

from .config import settings

API = "https://api.context.dev/v1"


def company(domain: str) -> dict[str, Any] | None:
    """The company behind `domain`, or None when nothing credible is known about it."""
    key = settings().context_dev_api_key
    if not key:
        raise RuntimeError("no CONTEXT_DEV_API_KEY configured")
    response = httpx.post(f"{API}/brand/retrieve", headers={"Authorization": f"Bearer {key}"},
                          json={"type": "by_domain", "domain": domain.lower().strip()}, timeout=45)
    if response.status_code != 200:
        return None
    brand = response.json().get("brand") or {}
    if not brand.get("title"):
        return None
    industries = ((brand.get("industries") or {}).get("eic") or [{}])
    logos = brand.get("logos") or [{}]
    return {
        "name": brand["title"],
        "domain": brand.get("domain") or domain,
        "description": brand.get("description"),
        "industry": industries[0].get("industry") if industries else None,
        "employees": (brand.get("employees") or {}).get("range"),
        "country": (brand.get("address") or {}).get("country_code"),
        "logo": logos[0].get("url") if logos else None,
    }
