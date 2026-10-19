"""A thin HubSpot client: bearer auth, JSON in and out, retries on 429 and 5xx, readable errors."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from .config import Settings, get_settings


class HubSpotError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"HubSpot {method} {path} -> {status}: {body[:400]}")
        self.status = status
        self.body = body


class HubSpot:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 4,
        sleep=time.sleep,
    ):
        s = settings or get_settings()
        if not s.hubspot_access_token and client is None:
            raise HubSpotError(
                "-", "-", 0, "HUBSPOT_ACCESS_TOKEN is empty: put the service key in .env"
            )
        self._client = client or httpx.Client(
            base_url=s.hubspot_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {s.hubspot_access_token}"},
            timeout=30,
        )
        self.max_retries = max_retries
        self._sleep = sleep

    def request(self, method: str, path: str, **kwargs) -> Any:
        for attempt in range(self.max_retries + 1):
            r = self._client.request(method, path, **kwargs)
            retryable = r.status_code == 429 or r.status_code >= 500
            if retryable and attempt < self.max_retries:
                wait = float(r.headers.get("Retry-After", 0) or 0) or 2**attempt
                self._sleep(min(wait, 30))
                continue
            if r.status_code >= 300:
                raise HubSpotError(method, path, r.status_code, r.text)
            return r.json() if r.content else {}
        raise HubSpotError(method, path, r.status_code, r.text)  # pragma: no cover

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, json=body)

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, json=body)

    def paged(self, path: str, key: str = "results", **params) -> Iterator[dict]:
        after = None
        while True:
            q = dict(params)
            if after:
                q["after"] = after
            data = self.get(path, **q)
            yield from data.get(key, [])
            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                return

    def search(
        self, object_type: str, filters: list[dict], properties: list[str], limit: int = 100
    ) -> list[dict]:
        body = {"filterGroups": [{"filters": filters}], "properties": properties, "limit": limit}
        return self.post(f"/crm/v3/objects/{object_type}/search", body).get("results", [])
