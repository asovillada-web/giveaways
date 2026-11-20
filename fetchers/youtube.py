"""Recent multilingual creator giveaways using YouTube Data API v3."""
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from config import WIDGET_HOSTS
from fetchers import RawItem, TIMEOUT
from links import extract_links

SEARCH_TERMS = {
    "en": ("giveaway", ("RTX", "GPU", "PS5", "Switch", "Steam", "PC", "keyboard", "mouse",
                        "headset", "monitor", "laptop", "phone")),
    "es": ("sorteo", ("RTX", "PS5", "Switch", "Steam", "PC", "teclado", "auriculares", "celular")),
    "pt": ("sorteio", ("RTX", "PS5", "Switch", "Steam", "PC", "teclado", "monitor", "celular")),
    "de": ("gewinnspiel", ("RTX", "PS5", "Switch", "Steam", "PC", "Tastatur", "Maus", "Laptop")),
    "fr": ("concours", ("RTX", "PS5", "Switch", "Steam", "PC", "clavier", "souris", "casque")),
}
API_ROOT = "https://www.googleapis.com/youtube/v3"


def query_specs(now: datetime):
    # Two domains per language per run. Rotate the pairs every three hours.
    slot = (int(now.timestamp()) // 10800) % 2
    for language, (giveaway, tech) in SEARCH_TERMS.items():
        for domain in WIDGET_HOSTS[2 * slot:2 * slot + 2]:
            query = "|".join(f'"{domain}" {giveaway} {term}' for term in tech)
            yield language, query


def api_get(client, operation: str, key: str, **params) -> dict:
    response = client.get(
        f"{API_ROOT}/{operation}", params={**params, "key": key},
        timeout=TIMEOUT, allow_redirects=False,
    )
    if response.status_code in {400, 403, 429}:
        errors = response.json().get("error", {}).get("errors", [])
        reason = errors[0].get("reason", "unavailable") if errors else "unavailable"
        raise ValueError(f"YouTube {operation} failed ({response.status_code}, {reason})")
    response.raise_for_status()
    return response.json()


def search(client, key: str, language: str, query: str, now: datetime) -> dict[str, str]:
    after = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = api_get(
        client, "search", key, part="snippet", type="video", q=query, maxResults=30,
        publishedAfter=after, order="date", relevanceLanguage=language, safeSearch="moderate",
        fields="items(id/videoId)",
    )
    return {item["id"]["videoId"]: language for item in data.get("items", []) if item.get("id", {}).get("videoId")}


def parse_videos(payload: dict, language_hints: dict[str, str], now: datetime) -> list[RawItem]:
    items = []
    for video in payload.get("items", []):
        video_id, snippet = video["id"], video["snippet"]
        try:
            published = datetime.fromisoformat(snippet.get("publishedAt", ""))
        except ValueError:
            continue
        if published.tzinfo is None or not now - timedelta(hours=48) <= published <= now:
            continue
        locale = snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage") or language_hints[video_id]
        language, _, country = locale.replace("_", "-").partition("-")
        description = snippet.get("description", "")
        for url in extract_links(description):
            if (urlsplit(url).hostname or "").removeprefix("www.") not in WIDGET_HOSTS:
                continue
            if not urlsplit(url).path.strip("/"):
                continue
            items.append(RawItem(
                title=snippet["title"], url=url, description=description, source_type="Creator",
                host=snippet.get("channelTitle", ""), language=language.lower(),
                country_hint=country.upper() if len(country) == 2 else "",
                source_url=f"https://www.youtube.com/watch?v={video_id}", published_at=published,
            ))
    return items


def details(client, key: str, found: dict[str, str], now: datetime) -> list[RawItem]:
    results = []
    ids = list(found)
    for index in range(0, len(ids), 50):
        payload = api_get(
            client, "videos", key, part="snippet", id=",".join(ids[index:index + 50]),
            fields="items(id,snippet(title,description,channelTitle,defaultLanguage,defaultAudioLanguage,publishedAt))",
        )
        results.extend(parse_videos(payload, found, now))
    return results
