"""Storefront evidence for limited-time, zero-price claims."""
from datetime import datetime
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from config import ADD_ON, FULL_GAME, Directory
from dates import parse_date
from fetchers import RawItem
from links import clean_url


def steam_specials(body: bytes, source: Directory) -> list[RawItem]:
    document = BeautifulSoup(body, "html.parser")
    results = document.select_one("#search_results")
    if results is None:
        raise ValueError("Steam storefront results are unavailable")
    items = []
    for row in results.select("a.search_result_row[href]")[:100]:
        text = row.select_one(".title")
        discount = row.select_one(".discount_pct")
        price = row.select_one("[data-price-final='0']")
        original_price = row.select_one(".discount_original_price")
        if not (text and discount and price and original_price):
            continue
        if discount.get_text(strip=True).replace("−", "-") != "-100%" or not original_price.get_text(strip=True):
            continue
        title = text.get_text(" ", strip=True)
        url = clean_url(urljoin(source.url, row["href"])).partition("?")[0]
        parts = urlsplit(url)
        if not title or parts.hostname != "store.steampowered.com" or not re.match(r"^/app/\d+(?:/|$)", parts.path):
            continue
        items.append(RawItem(
            title=title, url=url, description="Limited-time $0 full-game claim on Steam.",
            host=source.name, source_url=source.url, source_type=source.source_type, language="en",
            platform="Steam", guaranteed=True, freebie_kind=FULL_GAME, active_snapshot=True,
        ))
    return items


def epic_promotions(payload: dict, source: Directory, now: datetime) -> list[RawItem]:
    entries = payload["data"]["Catalog"]["searchStore"]["elements"]
    items = []
    for entry in entries:
        price = (entry.get("price") or {}).get("totalPrice") or {}
        if not price.get("originalPrice") or price.get("discountPrice") != 0 or entry.get("isCodeRedemptionOnly"):
            continue
        kind = {"BASE_GAME": FULL_GAME, "ADD_ON": ADD_ON, "DLC": ADD_ON}.get(entry.get("offerType"))
        title = entry.get("title")
        if not kind or not title:
            continue
        promotions = (entry.get("promotions") or {}).get("promotionalOffers") or []
        for group in promotions:
            for offer in group.get("promotionalOffers", []):
                setting = offer.get("discountSetting") or {}
                if setting.get("discountType") != "PERCENTAGE" or setting.get("discountPercentage") != 0:
                    continue
                start = parse_date(offer.get("startDate") or "", now)
                end = parse_date(offer.get("endDate") or "", now)
                if not (start and end and start <= now < end):
                    continue
                mappings = (entry.get("catalogNs") or {}).get("mappings") or entry.get("offerMappings") or []
                slug = next((m.get("pageSlug") for m in mappings if m.get("pageType") == "productHome" and m.get("pageSlug")),
                            entry.get("productSlug"))
                if slug and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", slug):
                    items.append(RawItem(
                        title=title, url=f"https://store.epicgames.com/en-US/p/{slug}",
                        description="Claim this limited-time $0 offer from the Epic Games Store.",
                        host=source.name, source_url="https://store.epicgames.com/en-US/free-games",
                        source_type=source.source_type, published_at=start, expires_at=end, language="en",
                        platform="Epic Games", guaranteed=True, freebie_kind=kind,
                    ))
    return items
