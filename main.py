"""Collect sources independently, merge observations, and deliver optional alerts."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from functools import partial
import logging
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
import requests

from config import DIRECTORIES, METADATA_HOSTS, SUBREDDITS
from db import Database
from fetchers import RawItem, TIMEOUT, session
from fetchers import directories, landing, reddit, youtube
from links import clean_url
from processor import process

logger = logging.getLogger("drop-radar")


def error_label(error: Exception) -> str:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    if isinstance(error, ValueError) and str(error).startswith(("YouTube ", "Reddit denied ", "Supabase ")):
        return str(error)
    return type(error).__name__


def run_fetch(fetch, *args, user_agent: str | None = None):
    with (session(user_agent) if user_agent else session()) as client:
        return fetch(client, *args)


def collect_youtube(key: str, now: datetime) -> list[RawItem]:
    found = {}
    successes = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = {pool.submit(run_fetch, youtube.search, key, language, query, now): language
                for language, query in youtube.query_specs(now)}
        for job in as_completed(jobs):
            try:
                for video_id, hint in job.result().items():
                    # Prefer a stable fallback if different language searches return the same video.
                    found[video_id] = min(hint, found.get(video_id, hint))
                successes += 1
            except (requests.RequestException, ValueError, KeyError) as error:
                logger.warning("YouTube search (%s) failed: %s", jobs[job], error_label(error))
    if not successes:
        raise ValueError("YouTube search failed for all five languages")
    return run_fetch(youtube.details, key, found, now)


def collect(now: datetime) -> tuple[list[RawItem], int]:
    user_agent = os.getenv("REDDIT_USER_AGENT") or "linux:drop-radar:v1.0 (giveaway aggregator)"
    work = [(source.name + " " + (source.platform if source.kind == "lootscraper" else source.kind),
             partial(run_fetch, directories.fetch_directory, source, now))
            for source in DIRECTORIES]
    try:
        token = run_fetch(reddit.authorize, user_agent=user_agent)
        work.extend((f"r/{subreddit}", partial(run_fetch, reddit.fetch_subreddit, subreddit, now, token,
                                              user_agent=user_agent)) for subreddit in SUBREDDITS)
    except (requests.RequestException, ValueError, KeyError) as error:
        logger.warning("Reddit authorization failed: %s", error_label(error))
    if key := os.getenv("YOUTUBE_API_KEY"):
        work.append(("YouTube", partial(collect_youtube, key, now)))
    else:
        logger.warning("YOUTUBE_API_KEY is unset; creator discovery is disabled")
    results, successes = [], 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch): (index, name) for index, (name, fetch) in enumerate(work)}
        batches = {}
        for job in as_completed(jobs):
            index, name = jobs[job]
            try:
                batch = job.result()
                batches[index] = batch
                logger.info("%s returned %d candidates", name, len(batch))
                successes += 1
            except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as error:
                logger.warning("%s failed: %s", name, error_label(error))
        for index in sorted(batches):
            results.extend(batches[index])
    return results, successes


def enrich(items: list[RawItem], now: datetime) -> dict[str, landing.Landing]:
    destinations = {}
    for item in items:
        url = clean_url(item.url)
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        if host in METADATA_HOSTS:
            destinations.setdefault(clean_url(url, canonical=True), (url, item.language))
    output = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        jobs = {pool.submit(run_fetch, landing.fetch_landing, url, now, language): key
                for key, (url, language) in list(destinations.items())[:80]}
        failed = 0
        for job in as_completed(jobs):
            try:
                output[jobs[job]] = job.result()
            except (requests.RequestException, ValueError) as error:
                failed += 1
                logger.debug("Landing probe failed: %s", error_label(error))
        if failed:
            logger.info("%d of %d landing probes unavailable; using source text", failed, len(jobs))
    return output


def send_alerts(database: Database, webhook: str) -> int:
    parts = urlsplit(webhook)
    if (parts.netloc not in {"discord.com", "canary.discord.com", "ptb.discord.com"}
            or parts.scheme != "https" or not parts.path.startswith("/api/webhooks/")):
        logger.error("DISCORD_WEBHOOK_URL must be an HTTPS Discord webhook URL")
        return 1
    failures = 0
    # Webhook POSTs have no idempotency key. A timeout is retried on a later lease.
    with requests.Session() as client:
        for item in database.claim_alerts():
            try:
                response = client.post(
                    webhook, params={"wait": "true"}, timeout=TIMEOUT, allow_redirects=False,
                    json={
                        "allowed_mentions": {"parse": []},
                        "embeds": [{
                            "title": item["title"], "url": item["original_url"],
                            "description": f'{item["category"]} • {item["region_scope"]}',
                            "color": 11706879 if item["category"] == "100% Freebie" else 16764289,
                        }],
                    },
                )
                if not response.ok or response.is_redirect:
                    logger.warning("Discord rejected an alert (HTTP %s)", response.status_code)
                    failures += 1
                    if response.status_code in {401, 403, 404, 429}:
                        break
                    continue
                database.finish_alert(item)
            except (requests.RequestException, ValueError) as error:
                logger.warning("Discord alert deferred: %s", error_label(error))
                failures += 1
    return int(bool(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Collect and classify without writing or sending alerts")
    parser.add_argument("--skip-metadata", action="store_true", help="Use source text without probing destinations")
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # urllib3 retry messages include the request path and query string.
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    now = datetime.now(UTC)

    with session() as client:
        try:
            database = None if args.dry_run else Database(
                client, os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"],
            )
        except (KeyError, ValueError) as error:
            logger.error("Worker configuration error: %s", error)
            return 1

        raw, successes = collect(now)
        metadata = {} if args.skip_metadata else enrich(raw, now)
        rows = []
        for item in sorted(raw, key=lambda offer: offer.published_at or datetime.min.replace(tzinfo=UTC)):
            page = metadata.get(clean_url(item.url, canonical=True), landing.Landing())
            try:
                if row := process(item, now, page):
                    rows.append(row)
            except (TypeError, ValueError) as error:
                logger.warning("Invalid source item skipped: %s", error_label(error))
        logger.info("%d relevant observations from %d successful fetchers: %s",
                    len(rows), successes, dict(Counter(row["category"] for row in rows)))
        if not successes:
            logger.error("All configured sources failed")
        if database is None:
            return int(not successes)

        try:
            if rows:
                logger.info("Recorded %d observations", database.record(rows))
            database.refresh()
            if webhook := os.getenv("DISCORD_WEBHOOK_URL"):
                if send_alerts(database, webhook):
                    return 1
        except (requests.RequestException, ValueError) as error:
            logger.error("Persistence failed: %s", error_label(error))
            return 1
    return int(not successes)


if __name__ == "__main__":
    raise SystemExit(main())
