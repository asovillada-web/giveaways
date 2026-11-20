"""Configured JSON, RSS/Atom, and selector-driven HTML sources."""
import calendar
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from config import Directory
from dates import parse_date
from fetchers import RawItem, TIMEOUT
from links import clean_url, destination_rank, extract_links

MAX_FEED_BYTES = 2_000_000


def limited_body(response, limit: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(8192):
        body.extend(chunk)
        if len(body) > limit:
            raise ValueError(f"Response exceeds {limit:,} bytes")
    return bytes(body)


def gamerpower(entries: list[dict], source: Directory, now: datetime) -> list[RawItem]:
    result = []
    for entry in entries:
        if (entry.get("status") or "").lower() != "active":
            continue
        expires = parse_date(entry.get("end_date") or "", now, deadline=True)
        published = parse_date(entry.get("published_date") or "", now)
        if (expires and expires <= now) or (
            not expires and published and published < now - timedelta(days=30)
        ):
            continue
        link = clean_url(entry.get("open_giveaway_url") or entry.get("open_giveaway") or "")
        if link and entry.get("title"):
            result.append(RawItem(
                title=entry["title"], url=link, description="\n".join(
                    str(entry.get(key) or "") for key in ("description", "instructions") if entry.get(key)
                ), host=source.name, source_type=source.source_type, language="en",
                source_url=entry.get("gamerpower_url") or source.url,
                published_at=published, expires_at=expires,
                platform=entry.get("platforms") or "",
                guaranteed=(entry.get("type") or "").casefold() in {"game", "dlc", "loot"},
            ))
    return result


def parsed_entry_time(entry) -> datetime | None:
    timestamp = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(timestamp), UTC) if timestamp else None


def rss(body: bytes, source: Directory, now: datetime) -> list[RawItem]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise ValueError("RSS/Atom feed is invalid")
    result = []
    for entry in feed.entries[:100]:
        published = parsed_entry_time(entry)
        if published and published < now - timedelta(days=7):
            continue
        if not entry.get("title") or not entry.get("link"):
            continue
        description = BeautifulSoup(entry.get("summary", ""), "html.parser")
        page = clean_url(urljoin(source.url, entry.link))
        if not page:
            continue
        links = [clean_url(urljoin(page, a["href"])) for a in description.select("a[href]")]
        links.extend(extract_links(description.get_text(" ", strip=True)))
        direct = max((link for link in links if link), key=destination_rank, default="")
        url = direct if direct and destination_rank(direct) >= 2 else page
        result.append(RawItem(
            title=entry.title, url=url, description=description.get_text(" ", strip=True),
            host=source.name, source_type=source.source_type, source_url=page,
            published_at=published, language=(feed.feed.get("language") or "").split("-")[0].lower(),
            platform=source.platform, guaranteed=source.guaranteed,
        ))
    return result


def html_listing(body: bytes, source: Directory) -> list[RawItem]:
    document = BeautifulSoup(body, "html.parser")
    result = []
    for item in document.select(source.item_selector)[:100]:
        anchor = item.select_one(source.link_selector)
        title = item.select_one(source.title_selector)
        description = item.select_one(source.description_selector) if source.description_selector else None
        if not title or not anchor or not anchor.get("href"):
            continue
        url = clean_url(urljoin(source.url, anchor["href"]))
        if url:
            result.append(RawItem(
                title=title.get_text(" ", strip=True), url=url,
                description=description.get_text(" ", strip=True) if description else "",
                host=source.name, source_type=source.source_type, source_url=source.url,
                platform=source.platform, guaranteed=source.guaranteed,
            ))
    return result


def fetch_directory(client, source: Directory, now: datetime) -> list[RawItem]:
    with client.get(source.url, timeout=TIMEOUT, stream=True) as response:
        if source.kind == "gamerpower" and response.status_code == 201:
            return []
        response.raise_for_status()
        body = limited_body(response, MAX_FEED_BYTES)
    if source.kind == "gamerpower":
        return gamerpower(json.loads(body), source, now)
    if source.kind == "rss":
        return rss(body, source, now)
    if source.kind == "html":
        return html_listing(body, source)
    raise ValueError(f"Unsupported directory kind {source.kind}")
