"""Bounded metadata probes against fixed publisher and giveaway-widget origins."""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from config import METADATA_HOSTS
from dates import ending_date, parse_date
from fetchers import TIMEOUT
from fetchers.directories import limited_body
from links import clean_url


@dataclass(frozen=True)
class Landing:
    title: str = ""
    text: str = ""
    expires_at: datetime | None = None
    expired: bool = False


def parse_landing(document: bytes, now: datetime, language: str) -> Landing:
    soup = BeautifulSoup(document, "html.parser")
    title_meta = soup.select_one('meta[property="og:title"]')
    title = title_meta.get("content", "") if title_meta else ""
    descriptions = [
        tag["content"][:3000] for tag in soup.select(
            'meta[name="description"][content], meta[property="og:description"][content]'
        )
    ]
    dates = []
    for tag in soup.select(
        '[itemprop="endDate"], [itemprop="availabilityEnds"], [itemprop="priceValidUntil"], '
        'meta[property="event:end_time"], meta[property="product:price:expiration_time"]'
    )[:20]:
        value = tag.get("content") or tag.get("datetime") or tag.get_text(strip=True)
        date = parse_date(value, now, language, deadline=True)
        if date:
            dates.append(date)
    stack = []
    for script in soup.select('script[type="application/ld+json"]')[:12]:
        try:
            stack.append(json.loads(script.string or ""))
        except (ValueError, RecursionError):
            continue
    for _ in range(300):
        if not stack:
            break
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node[:100])
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in {"endDate", "availabilityEnds", "priceValidUntil", "validThrough"} and isinstance(value, str):
                date = parse_date(value, now, language, deadline=True)
                if date:
                    dates.append(date)
            elif isinstance(value, (dict, list)):
                stack.append(value)
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    visible = (soup.body or soup).get_text("\n", strip=True)[:12000]
    snippets = re.findall(
        r"[^\n]{0,100}\b(?:worldwide|eligible|residents?|only|eligibility|international|expires?|"
        r"ends?|closes?|deadline|hasta|endet|jusqu|encerra|mondial|weltweit)\b[^\n]{0,160}",
        visible, re.I,
    )[:30]
    text = "\n".join([*descriptions, *snippets])
    expired = bool(re.search(
        r"(?:this (?:competition|contest|giveaway|promotion) (?:has ended|is closed)|"
        r"(?:competition|giveaway) (?:is )?(?:now )?closed)", visible[:4000], re.I
    ))
    return Landing(title, text, min(dates, default=None) or ending_date(text, now, language), expired)


def fetch_landing(client, url: str, now: datetime, language: str) -> Landing:
    for _ in range(3):
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        if host not in METADATA_HOSTS or not url.startswith("https://"):
            return Landing()
        with client.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = clean_url(urljoin(url, response.headers.get("location", "")))
                continue
            if response.status_code in {404, 410}:
                return Landing(expired=response.status_code == 410)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower():
                return Landing()
            return parse_landing(limited_body(response, 900_000), now, language)
    return Landing()
