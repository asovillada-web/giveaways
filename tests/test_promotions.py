from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock

from config import ADD_ON, FULL_GAME, GAME_KEY, SOFTWARE, Directory
from fetchers import RawItem
from fetchers.directories import giveawaybase_page, resolve_gamerpower_games, rss
from fetchers.promotions import epic_promotions, steam_specials
from processor import process

NOW = datetime(2026, 11, 19, 18, tzinfo=UTC)


class PromotionTests(TestCase):
    def test_steam_only_accepts_paid_games_with_a_full_discount(self):
        source = Directory("steam", "https://store.steampowered.com/search/", "Steam", source_type="Official")
        row = """
          <a class="search_result_row" href="https://store.steampowered.com/app/{id}/Example/?snr=1">
            <span class="title">Example {id}</span>
            <div data-price-final="{price}"><div class="discount_pct">{rate}</div>{original}</div>
          </a>
        """
        discount = '<div class="discount_original_price">$19.99</div>'
        body = '<div id="search_results">' + ''.join((
            row.format(id=1, price=0, rate="-100%", original=discount),
            row.format(id=2, price=0, rate="", original=""),
            row.format(id=3, price=99, rate="-95%", original=discount),
        )) + '</div>'
        offers = steam_specials(body.encode(), source)
        self.assertEqual([item.url for item in offers], ["https://store.steampowered.com/app/1/Example/"])
        row = process(offers[0], NOW)
        self.assertEqual(row["freebie_kind"], FULL_GAME)
        self.assertIsNone(row["expires_at"])
        self.assertEqual(row["verified_until"], (NOW + timedelta(hours=6)).isoformat())
        self.assertFalse(row["ending_soon"])

    def test_epic_rejects_permanent_free_and_upcoming_offers(self):
        source = Directory("epic", "https://store.epicgames.com/free-games", "Epic Games Store", source_type="Official")
        active = {
            "title": "Example game", "offerType": "BASE_GAME",
            "catalogNs": {"mappings": [{"pageSlug": "example-game", "pageType": "productHome"}]},
            "price": {"totalPrice": {"originalPrice": 1999, "discountPrice": 0}},
            "promotions": {"promotionalOffers": [{"promotionalOffers": [{
                "startDate": (NOW - timedelta(days=1)).isoformat(),
                "endDate": (NOW + timedelta(days=1)).isoformat(),
                "discountSetting": {"discountType": "PERCENTAGE", "discountPercentage": 0},
            }]}]},
        }
        entries = [
            active,
            {**active, "price": {"totalPrice": {"originalPrice": 0, "discountPrice": 0}}},
            {**active, "promotions": {"upcomingPromotionalOffers": active["promotions"]["promotionalOffers"]}},
            {**active, "isCodeRedemptionOnly": True},
        ]
        offers = epic_promotions({"data": {"Catalog": {"searchStore": {"elements": entries}}}}, source, NOW)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].url, "https://store.epicgames.com/en-US/p/example-game")
        self.assertEqual(offers[0].expires_at, NOW + timedelta(days=1))

    def test_gamerpower_redirect_keeps_previous_url_for_saved_state(self):
        item = RawItem(
            "Game (Epic Games) Giveaway", "https://www.gamerpower.com/open/example-game",
            source_url="https://www.gamerpower.com/example-game", host="GamerPower",
            guaranteed=True, freebie_kind=FULL_GAME,
        )
        client = MagicMock()
        response = client.get.return_value.__enter__.return_value
        response.is_redirect = True
        response.headers = {"Location": "https://store.epicgames.com/p/example-game"}
        result = process(resolve_gamerpower_games(client, [item])[0], NOW)
        self.assertEqual(result["canonical_url"], "https://store.epicgames.com/p/example-game")
        self.assertEqual(result["previous_canonical_urls"], ["https://gamerpower.com/example-game"])
        self.assertEqual(result["source_rank"], 1)

    def test_game_key_and_add_on_remain_distinct_types(self):
        item = RawItem("Claim a Steam key for a full game", "https://publisher.example/game",
                       guaranteed=True, freebie_kind=FULL_GAME)
        self.assertEqual(process(item, NOW)["freebie_kind"], GAME_KEY)
        loot = RawItem("Steam DLC content pack key", "https://publisher.example/loot",
                       guaranteed=True, freebie_kind=ADD_ON)
        self.assertEqual(process(loot, NOW)["freebie_kind"], ADD_ON)

    def test_active_asset_feed_honors_expiry_beyond_seven_days(self):
        source = Directory("lootscraper", "https://feed.eikowagenknecht.com/fab.xml",
                           "LootScraper", platform="Fab", freebie_kind=SOFTWARE)
        xml = b"""<rss version="2.0"><channel><item>
        <title>Fab (Asset, PC) - Forest Pack</title><link>https://www.fab.com/listings/forest</link>
        <pubDate>Tue, 10 Nov 2026 15:00:00 +0000</pubDate>
        <description>Offer valid from: 2026-11-10 15:00 Offer valid to: 2026-11-24 15:00 Claim it now for free.</description>
        </item></channel></rss>"""
        [item] = rss(xml, source, NOW)
        self.assertEqual(item.title, "Forest Pack")
        self.assertEqual(item.expires_at, datetime(2026, 11, 24, 15, tzinfo=UTC))
        self.assertEqual(process(item, NOW)["freebie_kind"], SOFTWARE)

    def test_software_feed_excludes_paid_discounts(self):
        source = Directory("shareware", "https://sharewareonsale.com/feed/", "SharewareOnSale",
                           platform="Software", freebie_kind=SOFTWARE)
        xml = b"""<rss version="2.0"><channel>
        <item><title>Utility One (100% discount)</title><link>https://sharewareonsale.com/s/free-utility</link></item>
        <item><title>Utility Two (75% discount)</title><link>https://sharewareonsale.com/s/paid-utility</link></item>
        </channel></rss>"""
        self.assertEqual([item.title for item in rss(xml, source, NOW)], ["Utility One"])

    def test_worldwide_gleam_contest_remains_a_draw(self):
        source = Directory("giveawaybase", "https://giveawaybase.com/feed/", "GiveawayBase")
        page = """<div class="entry-content"><p>STEP 1 - Enter through
        <a href="https://gleam.io/test123/giveaway">the giveaway widget</a></p>
        <h3>GIVEAWAY END: December 1, 2026</h3><h3>OPEN TO: WORLDWIDE</h3>
        <h3>GIVEAWAY PRIZE</h3><p>RTX 5090 GPU</p></div>"""
        item = giveawaybase_page(page.encode(), "Gaming Giveaway", "https://giveawaybase.com/example/",
                                 NOW, NOW, source)
        row = process(item, NOW)
        self.assertEqual(row["platform"], "Gleam")
        self.assertEqual(row["region_scope"], "Worldwide")
        self.assertEqual(row["category"], "Hardware & Devices")
        self.assertIsNone(row["freebie_kind"])
