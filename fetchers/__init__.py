"""Fetcher contract and HTTP defaults."""
from dataclasses import dataclass
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class RawItem:
    title: str
    url: str
    description: str = ""
    source_type: str = "Community"
    host: str = ""
    language: str = ""
    country_hint: str = ""
    source_url: str = ""
    published_at: datetime | None = None
    expires_at: datetime | None = None
    platform: str = ""
    guaranteed: bool = False
    freebie_kind: str = ""
    active_snapshot: bool = False
    eligibility: str = ""


def session(user_agent: str = "DropRadar/1.0 (giveaway aggregator)") -> requests.Session:
    client = requests.Session()
    client.headers["User-Agent"] = user_agent
    retries = Retry(
        total=1, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504),
        respect_retry_after_header=False,
    )
    client.mount("https://", HTTPAdapter(max_retries=retries))
    return client


TIMEOUT = (5, 12)
