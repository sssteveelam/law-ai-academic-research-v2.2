from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class Transport(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        ...
