from datetime import UTC, datetime, timedelta
import unittest

from config import Directory
from dates import ending_date
from eligibility import parse_region
from fetchers import RawItem
from fetchers.directories import gamerpower, html_listing, rss
from fetchers.landing import parse_landing
from fetchers.reddit import parse_listing
from fetchers.youtube import parse_videos, query_specs
from links import clean_url, extract_links
from processor import process

NOW = datetime(2026, 11, 19, 18, tzinfo=UTC)


class LinksTest(unittest.TestCase):
    def test_tracking_and_slugs(self):
        original = "https://www.gleam.io/AbC123/gaming-drop/?id=1&ref=Creator&utm_campaign=x"
        self.assertEqual(clean_url(original), "https://www.gleam.io/AbC123/gaming-drop/?id=1&ref=Creator&utm_campaign=x")
        self.assertEqual(clean_url(original, canonical=True), "https://gleam.io/AbC123?id=1")
        self.assertEqual(clean_url("https://store.epicgames.com/es-MX/p/game?lang=es", canonical=True),
                         "https://store.epicgames.com/p/game")

    def test_urls_with_credentials_and_local_urls_are_rejected(self):
        for url in ("javascript:alert(1)", "https://gleam.io@evil.com/path", "https://127.0.0.1",
                    "https://example.local", "https://example.com:8443/x", "http://www.example.com\\@evil.com/"):
            self.assertEqual(clean_url(url), "", url)

    def test_extract_exact_widget_links(self):
        text = ("[enter](https://gleam.io/AbC123/item?utm_source=youtube). "
                "sweepwidget.com/c/x-ps5 and https://example.com/gleam.io/not-a-campaign")
        self.assertEqual(extract_links(text), [
            "https://gleam.io/AbC123/item?utm_source=youtube", "https://example.com/gleam.io/not-a-campaign",
            "https://sweepwidget.com/c/x-ps5",
        ])


class EligibilityAndDatesTest(unittest.TestCase):
    def test_unspecified_and_explicit_worldwide(self):
        self.assertTrue(parse_region("Enter our GPU giveaway").worldwide)
        self.assertEqual(parse_region("Sorteo para todo el mundo").scope, "Worldwide")

    def test_explicit_scope_beats_global_claim(self):
        region = parse_region("Global giveaway. US and UK residents only.")
        self.assertFalse(region.worldwide)
        self.assertEqual(region.includes, ("GB", "US"))
        self.assertEqual(parse_region("EU only").scope, "EU")
        self.assertEqual(parse_region("U.S. only").scope, "US")
        self.assertEqual(parse_region("Exclusivo para América Latina").scope, "LATAM")

    def test_region_exceptions_and_ambiguous_restriction(self):
        self.assertEqual(parse_region("Worldwide except Canada and US").excludes, ("CA", "US"))
        self.assertEqual(parse_region("Region-locked.").scope, "Restricted")
        self.assertEqual(parse_region("Remote contest. Reply IN to enter.").scope, "Unspecified")

    def test_explicit_expiries_in_multiple_languages(self):
        self.assertEqual(ending_date("Ends Nov 20, 2026 8:00 PM EST", NOW),
                         datetime(2026, 11, 21, 1, tzinfo=UTC))
        self.assertEqual(ending_date("Hasta el 20 de noviembre de 2026", NOW, "es"),
                         datetime(2026, 11, 20, 23, 59, 59, tzinfo=UTC))
        self.assertEqual(ending_date("Gültig bis 20.11.2026", NOW, "de"),
                         datetime(2026, 11, 20, 23, 59, 59, tzinfo=UTC))
        self.assertEqual(ending_date("Expires November 20", NOW),
                         datetime(2026, 11, 20, 23, 59, 59, tzinfo=UTC))
        self.assertIsNone(ending_date("Originally published November 19, 2026", NOW))


class ClassificationTest(unittest.TestCase):
    def test_free_to_keep_and_urgency_score(self):
        item = RawItem("Free game to keep on Steam", "https://store.steampowered.com/app/99/Game",
                       "Claim your copy. Ends Nov 20, 2026 18:00 UTC")
        row = process(item, NOW)
        self.assertEqual(row["category"], "100% Freebie")
        self.assertEqual(row["priority_score"], 80)
        self.assertTrue(row["ending_soon"])

    def test_chance_and_paid_trials_are_not_freebies(self):
        draw = RawItem("Free Steam game giveaway", "https://gleam.io/AbC123/game",
                       "Enter to win", guaranteed=True)
        self.assertEqual(process(draw, NOW)["category"], "Games & Gift Cards")
        for title in ("Free trial weekend on Steam", "Free with subscription on Steam", "Free-to-play game giveaway"):
            self.assertIsNone(process(RawItem(title, "https://store.steampowered.com/app/99/Game"), NOW))

    def test_hardware_and_peripherals(self):
        hardware = RawItem("RTX 5090 GPU Giveaway, Worldwide", "https://gleam.io/AbC123/gpu")
        self.assertEqual(process(hardware, NOW)["priority_score"], 50)
        gear = RawItem("Wireless headset for PS5 giveaway", "https://gleam.io/AbC123/ps5")
        self.assertEqual(process(gear, NOW)["category"], "Peripherals & Gear")

    def test_spam_and_creator_locale_not_eligibility(self):
        self.assertIsNone(process(RawItem("Crypto giveaway free game", "https://gleam.io/AbC123/game"), NOW))
        item = RawItem("Sorteo RTX 5090", "https://gleam.io/AbC123/gpu",
                       source_type="Creator", language="es", country_hint="MX")
        row = process(item, NOW)
        self.assertEqual(row["region_scope"], "Unspecified")
        self.assertEqual(row["country_hint"], "MX")

    def test_landing_page_eligibility_and_end_date(self):
        page = parse_landing(b"""
            <meta property="og:title" content="RTX Giveaway">
            <meta property="og:description" content="Only open to Canadian residents.">
            <script type="application/ld+json">{"@type":"Event","endDate":"2026-11-20T10:00:00Z"}</script>
            <p>US only.</p>
            """, NOW, "en")
        row = process(RawItem("RTX Worldwide Giveaway", "https://gleam.io/AbC123/gpu"), NOW, page)
        self.assertEqual(row["region_scope"], "CA / US")
        self.assertEqual(row["expires_at"], "2026-11-20T10:00:00+00:00")
        self.assertEqual(row["priority_score"], 30)

    def test_gamerpower_api_and_rss_links_share_key(self):
        first = process(RawItem("Free Steam game", "https://www.gamerpower.com/open/free-game"), NOW)
        second = process(RawItem("Free Steam game", "https://www.gamerpower.com/free-game"), NOW)
        self.assertEqual(first["canonical_url"], second["canonical_url"])


class FetchersTest(unittest.TestCase):
    def test_reddit_picks_outbound_widget(self):
        post = {"created_utc": NOW.timestamp(), "title": "GPU giveaway", "selftext": "[Enter](https://gleam.io/AbC123/item)",
                "url": "https://www.reddit.com/r/pcmasterrace/comments/12/x/", "permalink": "/r/pcmasterrace/comments/12/x/"}
        rows = parse_listing({"data": {"children": [{"data": post}]}}, "pcmasterrace", NOW)
        self.assertEqual(rows[0].url, "https://gleam.io/AbC123/item")
        post["created_utc"] = (NOW - timedelta(hours=49)).timestamp()
        self.assertEqual(parse_listing({"data": {"children": [{"data": post}]}}, "pcmasterrace", NOW), [])

    def test_youtube_rotates_domains_within_quota(self):
        first = list(query_specs(NOW))
        second = list(query_specs(NOW + timedelta(hours=3)))
        self.assertEqual(len(first) + len(second), 20)
        self.assertEqual({lang for lang, _ in first}, {"en", "es", "pt", "de", "fr"})
        self.assertNotEqual(first, second)

    def test_youtube_prefers_reported_locale(self):
        data = {"items": [{"id": "video", "snippet": {
            "title": "Sorteo PS5", "channelTitle": "Creator", "publishedAt": NOW.isoformat(),
            "defaultLanguage": "es-MX", "description": "https://sweepwidget.com/c/ps5?ref=a",
        }}]}
        result = parse_videos(data, {"video": "en"}, NOW)
        self.assertEqual((result[0].host, result[0].language, result[0].country_hint), ("Creator", "es", "MX"))
        self.assertEqual(result[0].url, "https://sweepwidget.com/c/ps5?ref=a")

    def test_rss_and_html_external_links(self):
        feed = b"""<rss version="2.0"><channel><language>en</language><item>
        <title>Free Steam game</title><link>https://publisher.example/free-games</link>
        <description><![CDATA[<a href="https://store.steampowered.com/app/99/Game">Claim</a>]]></description>
        </item></channel></rss>"""
        result = rss(feed, Directory("rss", "https://publisher.example/promotions.xml", "Publisher"), NOW)
        self.assertIn("store.steampowered.com", result[0].url)
        html = b'<article><h2>GPU Giveaway</h2><p>Open worldwide.</p><a class="claim" href="/claim">Open</a></article>'
        result = html_listing(html, Directory("html", "https://publisher.example/promotions", "Publisher",
                                              "article", "h2", "p", "a.claim"))
        self.assertEqual(result[0].url, "https://publisher.example/claim")

    def test_gamerpower_keeps_fresh_or_timed_offers(self):
        item = {"status": "Active", "title": "Free Steam game", "type": "Game", "platforms": "Steam",
                "open_giveaway_url": "https://www.gamerpower.com/open/free-game"}
        rows = gamerpower([
            {**item, "published_date": "2025-01-01 00:00:00", "end_date": "N/A"},
            {**item, "published_date": "2025-01-01 00:00:00", "end_date": "2026-11-20 12:00:00"},
        ], Directory("gamerpower", "https://www.gamerpower.com/api/giveaways", "GamerPower"), NOW)
        self.assertTrue(rows[0].guaranteed)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
