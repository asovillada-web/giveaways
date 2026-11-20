"""Only the scheduled worker holds a Supabase write key."""
from itertools import islice
from urllib.parse import urlsplit

import requests

from fetchers import TIMEOUT
from links import clean_url


class Database:
    def __init__(self, client: requests.Session, url: str, key: str):
        self.client = client
        origin = clean_url(url)
        parts = urlsplit(origin)
        if not origin.startswith("https://") or parts.path != "/" or parts.query or parts.fragment:
            raise ValueError("SUPABASE_URL must be the HTTPS project origin")
        if not key or key.startswith("sb_publishable_"):
            raise ValueError("SUPABASE_SERVICE_KEY must be a backend secret or service_role key")
        self.root = f"{origin.rstrip('/')}/rest/v1/rpc"
        self.headers = {"apikey": key}
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {key}"

    def call(self, operation: str, payload: dict | None = None):
        response = self.client.post(
            f"{self.root}/{operation}", headers=self.headers,
            json=payload or {}, timeout=TIMEOUT, allow_redirects=False,
        )
        if not response.ok or response.is_redirect:
            # Database errors may include row contents.
            raise ValueError(f"Supabase {operation} failed (HTTP {response.status_code})")
        return response.json() if response.content else None

    def record(self, items: list[dict]) -> int:
        ordered = iter(sorted(items, key=lambda row: row["canonical_url"]))
        saved = 0
        while batch := list(islice(ordered, 100)):
            saved += self.call("record_giveaways", {"items": batch})
        return saved

    def refresh(self) -> None:
        self.call("refresh_giveaways")

    def claim_alerts(self) -> list[dict]:
        return self.call("claim_giveaway_alerts")

    def finish_alert(self, item: dict) -> None:
        self.call("finish_giveaway_alert", {"giveaway_id": item["id"], "lease_token": item["alert_token"]})
