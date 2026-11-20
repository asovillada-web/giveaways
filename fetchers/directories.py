"""Configured JSON, RSS/Atom, and selector-driven HTML sources."""
import calendar
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

import feedparser
from bs4 import BeautifulSoup
import requests

from config import ADD_ON, EPIC_ANDROID, EPIC_IOS, FULL_GAME, GAME_KEY, NOT_FREE, Directory
from dates import ending_date, parse_date
from fetchers import RawItem, TIMEOUT
from fetchers.promotions import epic_promotions, steam_specials
from links import clean_url, destination_rank, extract_links, platform_for

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
            kind = {"game": FULL_GAME, "dlc": ADD_ON, "loot": ADD_ON}.get((entry.get("type") or "").casefold(), "")
            result.append(RawItem(
                title=entry["title"], url=link, description="\n".join(
                    str(entry.get(key) or "") for key in ("description", "instructions") if entry.get(key)
                ), host=source.name, source_type=source.source_type, language="en",
                source_url=entry.get("gamerpower_url") or source.url,
                published_at=published, expires_at=expires,
                platform=entry.get("platforms") or "",
                guaranteed=bool(kind), freebie_kind=kind, active_snapshot=True,
            ))
    return result


def resolve_gamerpower_games(client, items: list[RawItem]) -> list[RawItem]:
    """Resolve first-party redirect links without visiting arbitrary destinations."""
    budget = 8
    result = []
    eligible = {"Steam", "Epic Games", EPIC_ANDROID, EPIC_IOS, "GOG", "itch.io", "Humble Bundle"}
    for item in items:
        parts = urlsplit(item.url)
        if (budget and item.freebie_kind == FULL_GAME and (parts.hostname or "").removeprefix("www.") == "gamerpower.com"
                and parts.path.startswith("/open/") and not re.search(r"\b(?:keys?|codes?)\b", item.title, re.I)):
            budget -= 1
            try:
                with client.get(item.url, timeout=(3, 5), stream=True, allow_redirects=False) as response:
                    direct = clean_url(response.headers.get("Location", "")) if response.is_redirect else ""
                if direct and platform_for(direct) in eligible and urlsplit(direct).path.strip("/"):
                    item = replace(item, url=direct)
            except requests.RequestException:
                pass
        result.append(item)
    return result


def parsed_entry_time(entry) -> datetime | None:
    timestamp = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(timestamp), UTC) if timestamp else None


def giveawaybase_page(body: bytes, title: str, page: str, published: datetime,
                      now: datetime, source: Directory) -> RawItem | None:
    content = BeautifulSoup(body, "html.parser").select_one(".entry-content")
    if content is None:
        return None
    headings = {tag.get_text(" ", strip=True).upper().partition(":")[0].strip(): tag
                for tag in content.select("h2,h3,h4")}
    deadline = headings.get("GIVEAWAY END")
    expires = ending_date(deadline.get_text(" ", strip=True), now, "en") if deadline else None
    if not expires or expires <= now:
        return None
    url = ""
    for step in content.select("p"):
        if re.match(r"^STEP\s+1\b", step.get_text(" ", strip=True), re.I):
            if anchor := step.select_one("a[href]"):
                url = clean_url(urljoin(page, anchor["href"]))
                break
    if not url or urlsplit(url).hostname == urlsplit(page).hostname:
        return None
    eligibility = headings.get("OPEN TO")
    prize_heading = headings.get("GIVEAWAY PRIZE")
    prize = prize_heading.find_next_sibling() if prize_heading else None
    details = [prize.get_text(" ", strip=True)[:230] if prize else "", "Enter for a chance to win."]
    if eligibility:
        details.append(eligibility.get_text(" ", strip=True))
    return RawItem(
        title=title, url=url, description="\n".join(filter(None, details)), host=source.name,
        published_at=published, expires_at=expires, source_url=page, language="en",
    )


def giveawaybase(client, source: Directory, now: datetime) -> list[RawItem]:
    feeds = []
    for url in (source.url, *source.more_feeds):
        try:
            with client.get(url, timeout=TIMEOUT, stream=True) as response:
                response.raise_for_status()
                feeds.append(feedparser.parse(limited_body(response, MAX_FEED_BYTES)))
        except (requests.RequestException, ValueError):
            continue
    feeds = [feed for feed in feeds if not feed.bozo or feed.entries]
    if not feeds:
        raise ValueError("GiveawayBase RSS is unavailable")
    pages = set()
    items = []
    for entry in (entry for feed in feeds for entry in feed.entries[:10]):
        published = parsed_entry_time(entry)
        page = clean_url(entry.get("link") or "")
        if (not published or not now - timedelta(days=7) <= published <= now or not entry.get("title")
                or page in pages or urlsplit(page).hostname != "giveawaybase.com"):
            continue
        pages.add(page)
        try:
            with client.get(page, timeout=(3, 5), stream=True, allow_redirects=False) as response:
                if response.is_redirect:
                    continue
                response.raise_for_status()
                page_body = limited_body(response, 700_000)
        except (requests.RequestException, ValueError):
            continue
        if item := giveawaybase_page(page_body, entry.title, page, published, now, source):
            items.append(item)
    return items


def claim_feed_entry(entry, source: Directory, now: datetime, page: str,
                     published: datetime | None, text: str) -> RawItem | None:
    title = entry.title
    expires = None
    kind = source.freebie_kind
    eligibility = ""
    if source.kind == "lootscraper":
        if not platform_for(page) or platform_for(page) != source.platform:
            return None
        start = re.search(r"Offer valid from:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text, re.I)
        end = re.search(r"Offer valid to:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text, re.I)
        if start and (starts_at := parse_date(start[1], now)) and starts_at > now:
            return None
        expires = parse_date(end[1], now) if end else None
        if source.platform in {EPIC_ANDROID, EPIC_IOS} and not expires:
            return None
        title = re.sub(r"^[^()]+ \([^)]*\) - ", "", title, count=1)
        if re.search(r"\b(play for free|free[ -]to[ -]play|free weekend|trial)\b", f"{title} {text}", re.I):
            return None
        if re.search(r"\b(?:redeem|claim) (?:your |a )?(?:steam |game )?(?:key|code)\b", text, re.I):
            if kind == FULL_GAME:
                kind = GAME_KEY
        description = f"Limited-time free offer on {source.platform}."
        if source.platform == EPIC_IOS:
            eligibility = "Available in the European Union, Japan, and Brazil."
            description += " iPad availability is limited to the EU."
    elif source.kind == "daily_software":
        if not published or (urlsplit(page).hostname or "").removeprefix("www.") != "giveawayoftheday.com":
            return None
        expires = published + timedelta(hours=24)
        description = "Daily software giveaway. Check the download, activation, and license terms."
    else:
        if (urlsplit(page).hostname or "").removeprefix("www.") != "sharewareonsale.com" or not re.search(r"\(100% discount\)$", title, re.I):
            return None
        title = re.sub(r"\s*\(100% discount\)$", "", title, flags=re.I)
        description = "Software giveaway at $0. Check the activation and license terms on the offer page."
    if ((expires and expires <= now) or (published and published > now)
            or re.search(NOT_FREE, f"{title} {text}", re.I)):
        return None
    return RawItem(
        title=title, url=page, description=description, host=source.name, source_type=source.source_type,
        source_url=page if source.kind != "lootscraper" else "https://github.com/eikowagenknecht/lootscraper#rss-feeds",
        published_at=published, expires_at=expires, language="en", platform=source.platform,
        guaranteed=True, freebie_kind=kind, active_snapshot=True, eligibility=eligibility,
    )


def rss(body: bytes, source: Directory, now: datetime) -> list[RawItem]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise ValueError("RSS/Atom feed is invalid")
    result = []
    for entry in feed.entries[:100]:
        published = parsed_entry_time(entry)
        if source.kind == "rss" and published and published < now - timedelta(days=7):
            continue
        if not entry.get("title") or not entry.get("link"):
            continue
        description = BeautifulSoup(entry.get("summary", ""), "html.parser")
        page = clean_url(urljoin(source.url, entry.link))
        if not page:
            continue
        text = description.get_text(" ", strip=True)
        if source.kind != "rss":
            if item := claim_feed_entry(entry, source, now, page, published, text):
                result.append(item)
            continue
        links = [clean_url(urljoin(page, a["href"])) for a in description.select("a[href]")]
        links.extend(extract_links(text))
        direct = max((link for link in links if link), key=destination_rank, default="")
        url = direct if direct and destination_rank(direct) >= 2 else page
        result.append(RawItem(
            title=entry.title, url=url, description=text,
            host=source.name, source_type=source.source_type, source_url=page,
            published_at=published, language=(feed.feed.get("language") or "").split("-")[0].lower(),
            platform=source.platform, guaranteed=source.guaranteed, freebie_kind=source.freebie_kind,
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
                platform=source.platform, guaranteed=source.guaranteed, freebie_kind=source.freebie_kind,
            ))
    return result


def fetch_directory(client, source: Directory, now: datetime) -> list[RawItem]:
    if source.kind == "giveawaybase":
        return giveawaybase(client, source, now)
    with client.get(source.url, timeout=TIMEOUT, stream=True) as response:
        if source.kind == "gamerpower" and response.status_code == 201:
            return []
        response.raise_for_status()
        body = limited_body(response, MAX_FEED_BYTES)
    if source.kind == "gamerpower":
        return resolve_gamerpower_games(client, gamerpower(json.loads(body), source, now))
    if source.kind in {"rss", "lootscraper", "daily_software", "shareware"}:
        return rss(body, source, now)
    if source.kind == "steam":
        return steam_specials(body, source)
    if source.kind == "epic":
        return epic_promotions(json.loads(body), source, now)
    if source.kind == "html":
        return html_listing(body, source)
    raise ValueError(f"Unsupported directory kind {source.kind}")
