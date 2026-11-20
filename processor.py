"""Normalize offers and apply category, region, expiry, and ranking rules."""
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from config import (
    ADD_ON, BLOCKLIST, CHANCE, DIGITAL, FREE_CLAIM, FULL_GAME, GAME_KEY, GEAR, GIVEAWAY,
    HARDWARE, NOT_FREE, OTHER_FREEBIE, SOFTWARE, WIDGET_HOSTS,
)
from dates import ending_date
from eligibility import parse_region
from fetchers import RawItem
from fetchers.landing import Landing
from links import clean_url, platform_for

CAT_FREE = "100% Freebie"
CAT_HW = "Hardware & Devices"
CAT_GEAR = "Peripherals & Gear"
CAT_GAME = "Games & Gift Cards"
STORE_PLATFORMS = {"Steam", "Epic Games", "GOG", "itch.io"}
WIDGET_PLATFORMS = {platform_for("https://" + host) for host in WIDGET_HOSTS}
GAME_KEY_TEXT = (
    r"\b(?:steam|game|activation|redemption|serial|license)\s+(?:keys?|codes?)\b"
    r"|\b(?:claim|grab|redeem)\s+(?:your |a )?(?:free )?(?:keys?|codes?)\b"
)
ADD_ON_TEXT = (
    r"\b(?:dlc|in[ -]game loot|content pack|expansion pack|outfit|skin key|"
    r"skin pack|cosmetic pack|item pack|gift pack|bloodpoints|currency pack|add[ -]on)\b"
)


def matches(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.I))


def plain(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True) if "<" in text else text


def summary(text: str, maximum: int) -> str:
    text = " ".join(re.sub(r"https?://\S+", "", plain(text)).split())
    return text if len(text) <= maximum else text[:maximum - 1].rstrip() + "…"


def classify(item: RawItem, url: str, landing: Landing) -> tuple[str, str, int] | None:
    title = plain(item.title)
    description = plain(item.description)[:10000]
    text = f"{title}\n{description}"
    listing = f"{title}\n{landing.title}"
    if matches(BLOCKLIST, title) or matches(BLOCKLIST, f"{description[:500]}\n{landing.title}"):
        return None
    if matches(r"\b(?:request(?:ing)?(?: a| for)?|looking for)(?: free| a)? (?:steam|game|key)|\[(?:request|closed|expired)\]", title):
        return None

    platform = platform_for(url)
    platform_hint = f"{item.platform} {title}"
    if not platform or platform == "GamerPower":
        for brand, hint in {
            "Steam": r"\bsteam\b", "Epic Games": r"\bepic(?: games)?\b", "GOG": r"\bgog\b",
            "itch.io": r"\bitch\.io\b", "Xbox": r"\bxbox\b", "PlayStation": r"\b(?:playstation|ps[45])\b",
            "Nintendo": r"\b(?:nintendo|switch)\b",
        }.items():
            if matches(hint, platform_hint):
                platform = brand
                break
    platform = platform or (item.platform if item.freebie_kind else "")

    hardware = matches(HARDWARE, listing)
    gear = matches(GEAR, listing)
    digital = matches(DIGITAL, text) or platform in STORE_PLATFORMS or item.guaranteed
    if item.source_type == "Official" or item.host == "GiveawayBase" or not (hardware or gear or digital):
        hardware = hardware or matches(HARDWARE, description[:1000])
        gear = gear or matches(GEAR, description[:1000])
    if not (hardware or gear or digital):
        return None
    if item.source_type == "Creator" and not matches(GIVEAWAY, f"{text}\n{landing.text}"):
        return None

    if item.source_type == "Official" and item.guaranteed and item.freebie_kind:
        return CAT_FREE, platform or "Other", 4
    claim_text = text if item.guaranteed and item.freebie_kind else f"{text}\n{landing.text}"
    uncertain = platform in WIDGET_PLATFORMS or matches(CHANCE, claim_text)
    paid_or_trial = matches(NOT_FREE, claim_text)
    if paid_or_trial and not uncertain:
        return None
    if digital and not uncertain and not paid_or_trial and (item.guaranteed or matches(FREE_CLAIM, claim_text)):
        return CAT_FREE, platform or "Other", 4 if item.guaranteed else 3
    # A game or store card for a console is a digital prize.
    if digital and matches(r"\b(?:game key|game code|gift card|store credit|tarjeta regalo|carte cadeau|"
                           r"game pass|dlc|playstation store|steam wallet|eshop)\b", title):
        return CAT_GAME, platform or "Other", 2
    if gear and (not hardware or matches(r"\b(?:for|para|f[uü]r|pour)\s+(?:the\s+)?(?:ps[45]|xbox|switch|pc)\b", title)):
        return CAT_GEAR, platform or "Other", 2
    if hardware:
        return CAT_HW, platform or "Other", 2
    if gear:
        return CAT_GEAR, platform or "Other", 2
    if item.source_type == "Creator" and not matches(DIGITAL, text):
        return None
    return CAT_GAME, platform or "Other", 1


def freebie_kind(item: RawItem, title: str) -> str:
    if item.freebie_kind:
        if (item.freebie_kind == FULL_GAME and item.source_type != "Official"
                and matches(GAME_KEY_TEXT, f"{title}\n{plain(item.description)[:500]}")):
            return GAME_KEY
        return item.freebie_kind
    if matches(ADD_ON_TEXT, title):
        return ADD_ON
    if matches(r"\b(?:software|utilities|software license|app licence)\b", title):
        return SOFTWARE
    if matches(GAME_KEY_TEXT, title):
        return GAME_KEY
    if matches(r"\b(?:full game|free (?:pc )?games?|game to keep)\b", title):
        return FULL_GAME
    return OTHER_FREEBIE


def score(category: str, worldwide: bool, ending_soon: bool) -> int:
    return (40 * (category == CAT_FREE) + 30 * worldwide
            + 20 * (category == CAT_HW) + 10 * ending_soon)


def process(item: RawItem, now: datetime, landing: Landing = Landing()) -> dict | None:
    url = clean_url(item.url)
    title = summary(item.title, 200)
    if not url or not title:
        return None
    label = classify(item, url, landing)
    if label is None:
        return None
    category, platform, category_confidence = label
    context = f"{item.title}\n{plain(item.description)[:10000]}"
    region = parse_region(item.eligibility or f"{context}\n{landing.text}")
    estimated = ending_date(context, now, item.language)
    if item.expires_at and (item.source_type == "Official" or (item.guaranteed and item.freebie_kind)):
        expires, confidence = item.expires_at, 4 if item.source_type == "Official" else 2
    else:
        expires = landing.expires_at or item.expires_at or estimated
        confidence = 3 if landing.expires_at else 2 if item.expires_at else 1 if estimated else 0
    if landing.expired and not (item.source_type == "Official" and item.expires_at) and (not expires or expires > now):
        expires, confidence = now, 3
    urgent = bool(expires and now < expires <= now + timedelta(hours=48))
    source_rank = {"Official": 4, "Creator": 3, "Community": 2}.get(item.source_type, 1)
    if item.host == "GamerPower" or platform_for(url) == "GamerPower":
        source_rank = 1
    canonical = clean_url(url, canonical=True)
    if platform_for(url) == "GamerPower":
        parts = urlsplit(canonical)
        if parts.path.startswith("/open/"):
            canonical = urlunsplit(parts._replace(path=parts.path.removeprefix("/open")))
    source_url = clean_url(item.source_url)
    previous_url = clean_url(source_url, canonical=True) if (
        item.host == "GamerPower" and platform_for(source_url) == "GamerPower" and platform_for(url) != "GamerPower"
    ) else ""
    return {
        "canonical_url": canonical,
        "previous_canonical_urls": [previous_url] if previous_url else [],
        "original_url": url,
        "title": title,
        "prize_summary": summary(landing.text if item.source_type == "Creator" else item.description, 340) or title,
        "category": category,
        "freebie_kind": freebie_kind(item, title) if category == CAT_FREE else None,
        "platform": platform,
        "source_type": item.source_type,
        "creator_or_host": summary(item.host, 120) or (urlsplit(url).hostname or "Unknown"),
        "language": item.language[:12] or "und",
        "country_hint": item.country_hint or None,
        "source_url": source_url or None,
        "region_scope": region.scope,
        "is_worldwide": region.worldwide,
        "region_codes": list(region.includes),
        "region_exclusions": list(region.excludes),
        "priority_score": score(category, region.worldwide, urgent),
        "expires_at": expires.isoformat() if expires else None,
        "verified_until": (now + timedelta(hours=6)).isoformat() if item.active_snapshot and not expires else None,
        "is_expired": bool(expires and expires <= now),
        "ending_soon": urgent,
        "source_rank": source_rank,
        "category_confidence": category_confidence,
        "region_confidence": 4 if item.eligibility and region.evidence else region.evidence,
        "expires_confidence": confidence,
    }
