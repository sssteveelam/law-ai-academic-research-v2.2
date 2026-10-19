from __future__ import annotations

from typing import Any

from clients.base import Transport
from clients.http import JSONClient
from core.cache import JsonFileCache


class UnpaywallClient(JSONClient):
    """Lawful OA metadata lookup; it never bypasses publisher access controls."""

    endpoint = "https://api.unpaywall.org/v2"

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        email: str,
        timeout: float = 20,
        cache: JsonFileCache | None = None,
        max_retries: int = 3,
        sleep=None,
    ) -> None:
        if not email.strip():
            raise ValueError("Unpaywall requires a contact email")
        kwargs: dict[str, Any] = {
            "transport": transport,
            "timeout": timeout,
            "cache": cache,
            "max_retries": max_retries,
        }
        if sleep is not None:
            kwargs["sleep"] = sleep
        super().__init__(**kwargs)
        self.email = email

    def lookup(self, doi: str) -> dict[str, Any]:
        normalized = doi.strip().lower()
        url = f"{self.endpoint}/{normalized}"
        params = {"email": self.email}
        return self.get_json(
            url,
            params,
            headers={"Accept": "application/json"},
            namespace="unpaywall",
            cache_key=f"{url}?email={self.email}",
        )
