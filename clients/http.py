from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from clients.base import Transport
from core.cache import JsonFileCache
from core.errors import ExternalAPIError


class JSONClient:
    """Shared bounded-retry JSON transport for scholarly API adapters."""

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        timeout: float = 20,
        cache: JsonFileCache | None = None,
        max_retries: int = 3,
        sleep=time.sleep,
        min_request_interval_seconds: float = 0.0,
        clock=time.monotonic,
    ) -> None:
        self.transport = transport or httpx.Client()
        self.timeout = timeout
        self.cache = cache
        self.max_retries = max_retries
        self.sleep = sleep
        self.min_request_interval_seconds = max(0.0, min_request_interval_seconds)
        self.clock = clock
        self._last_request_at: float | None = None

    def get_json(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        namespace: str,
        cache_key: str,
    ) -> dict[str, Any]:
        if self.cache:
            cached = self.cache.get(namespace, cache_key)
            if isinstance(cached, dict):
                return cached
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._wait_for_rate_limit()
                response = self.transport.get(
                    endpoint,
                    params=dict(params),
                    headers=dict(headers or {}),
                    timeout=self.timeout,
                )
                status = response.status_code
                if status == 200:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ExternalAPIError(f"{namespace} returned a non-object payload")
                    if self.cache:
                        self.cache.set(namespace, cache_key, payload)
                    return payload
                if status not in (429, 500, 502, 503, 504):
                    raise ExternalAPIError(f"{namespace} HTTP {status}")
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.replace(".", "", 1).isdigit()
                    else 2**attempt
                )
                if attempt < self.max_retries:
                    self.sleep(delay)
                    continue
                raise ExternalAPIError(f"{namespace} HTTP {status} after retries")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self.sleep(2**attempt)
                    continue
                raise ExternalAPIError(
                    f"{namespace} request failed after retries"
                ) from exc
        raise ExternalAPIError(f"{namespace} request failed") from last_error

    def _wait_for_rate_limit(self) -> None:
        if self.min_request_interval_seconds <= 0 or self._last_request_at is None:
            self._last_request_at = self.clock()
            return
        elapsed = self.clock() - self._last_request_at
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self.sleep(remaining)
        self._last_request_at = self.clock()
