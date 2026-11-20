"""Reddit listings via public JSON or an approved app-only OAuth client."""
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from config import GIVEAWAY
from fetchers import RawItem, TIMEOUT
from links import clean_url, destination_rank, extract_links

FREE_SUBS = {"freegamefindings", "freegames"}


def authorize(client) -> str:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id and not secret:
        return ""
    if not client_id or not secret:
        raise ValueError("Set both REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
    response = client.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(client_id, secret), data={"grant_type": "client_credentials"},
        timeout=TIMEOUT, allow_redirects=False,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def parse_listing(payload: dict, subreddit: str, now: datetime) -> list[RawItem]:
    items = []
    for node in payload.get("data", {}).get("children", []):
        post = node.get("data", {})
        if post.get("stickied") or post.get("over_18") or post.get("removed_by_category"):
            continue
        title, body, flair = (post.get(key) or "" for key in ("title", "selftext", "link_flair_text"))
        if re.search(r"\b(?:expired|closed|ended|completed)\b", flair, re.I):
            continue
        if not re.search(GIVEAWAY, f"{title} {flair} {body[:2000]}", re.I) and (
            subreddit.lower() not in FREE_SUBS | {"steamgiveaway"}
        ):
            continue
        try:
            published = datetime.fromtimestamp(post["created_utc"], UTC)
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            continue
        if not now - timedelta(hours=48) <= published <= now + timedelta(minutes=5):
            continue
        permalink = post.get("permalink") or ""
        thread = clean_url(f"https://www.reddit.com{permalink}") if permalink.startswith("/r/") else ""
        outgoing = clean_url(post.get("url_overridden_by_dest") or post.get("url") or "")
        links = extract_links(body)
        known = [url for url in links if destination_rank(url) >= 2]
        if outgoing and destination_rank(outgoing) > 0:
            urls = [outgoing, *known] if destination_rank(outgoing) >= 2 else known or [outgoing]
        else:
            urls = known or [url for url in links if destination_rank(url) > 0][:1]
        for url in dict.fromkeys(urls or [thread]):
            if url:
                host = urlsplit(url).hostname or ""
                guaranteed = subreddit.lower() in FREE_SUBS and (
                    "[game]" in title.lower() or "[dlc]" in title.lower() or "[software]" in title.lower()
                ) and destination_rank(url) == 2 and host != "www.gamerpower.com"
                items.append(RawItem(
                    title=title, url=url, description=f"{body}\n{flair}", host=f"r/{subreddit}",
                    source_url=thread, published_at=published, guaranteed=guaranteed,
                    platform="Steam" if subreddit.lower() == "steamgiveaway" else "",
                ))
    return items


def fetch_subreddit(client, subreddit: str, now: datetime, token: str) -> list[RawItem]:
    root = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    route = "new" if token else "new.json"
    response = client.get(
        f"{root}/r/{subreddit}/{route}", params={"limit": 75, "raw_json": 1},
        headers={"Authorization": f"Bearer {token}"} if token else {},
        timeout=TIMEOUT, allow_redirects=False,
    )
    if response.status_code in {401, 403}:
        raise ValueError("Reddit denied access. Hosted runners may require approved OAuth credentials.")
    response.raise_for_status()
    return parse_listing(response.json(), subreddit, now)
