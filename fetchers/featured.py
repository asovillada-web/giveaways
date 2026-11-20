"""Current campaigns checked against sponsor announcements and entry pages."""
from datetime import datetime

from fetchers import RawItem


def draw(host: str, title: str, url: str, end: str, prize: str, *,
         eligibility: str = "", source_url: str = "", start: str = "") -> RawItem:
    return RawItem(
        title=title, url=url, description=f"Enter for a chance to win {prize}", host=host,
        source_type="Official", source_url=source_url or url, language="en", eligibility=eligibility,
        published_at=datetime.fromisoformat(start) if start else None,
        expires_at=datetime.fromisoformat(end),
    )


CAMPAIGNS = (
    draw("ASUS ROG", "ROG Ace Your Setup giveaway",
         "https://gleam.io/ca47Z/rog-ace-your-setup-giveaway", "2026-12-13T15:59:59Z",
         "a ROG keyboard, gaming mouse, headset, and esports monitor bundle, or individual ROG gear.",
         start="2026-11-10T13:00:00Z", eligibility="Open worldwide.",
         source_url="https://rog.asus.com/event/ace-your-setup-giveaway/"),
    draw("ASUS ROG", "ROG 20th anniversary Zephyrus G16 giveaway",
         "https://gleam.io/giveaways/e9qBg", "2026-11-24T07:59:00Z",
         "a custom ROG Zephyrus G16 gaming laptop.", eligibility="US only."),
    draw("Gleam.io", "PlayStation 5 Pro and Grand Theft Auto giveaway",
         "https://gleam.io/giveaways/gB6Mc", "2026-11-30T12:59:00Z",
         "a PlayStation 5 Pro console with Grand Theft Auto.", eligibility="Open worldwide."),
    draw("Gleam.io", "Apple MacBook Neo giveaway",
         "https://gleam.io/giveaways/3tR8E", "2026-12-31T12:59:00Z",
         "an Apple MacBook Neo.", eligibility="Open worldwide."),
    draw("Lenovo Legion", "Lenovo Legion Pro 32UD-10 monitor giveaway",
         "https://gaming.lenovo.com/giveaways/post/na-eu-uk-jp-november-2026-giveaway---legion-pro-32ud-10-L0Eyz1e3Y0vczUx",
         "2026-12-02T04:59:00Z", "one of three Legion Pro 32UD-10 gaming monitors.",
         eligibility="Open to residents of the United States, Canada, United Kingdom, European Union, and Japan."),
    draw("REDMAGIC", "JerryRigEverything's REDMAGIC 12 Pro giveaway",
         "https://gleam.io/giveaways/Vp1JC", "2026-11-22T11:00:00Z",
         "one of three REDMAGIC 12 Pro gaming phones with 16 GB of RAM and 512 GB of storage."),
    draw("Logitech G", "Logitech G ASTRO A50 X headset giveaway",
         "https://gleam.io/giveaways/iHDZW", "2027-01-02T07:59:00Z",
         "an ASTRO A50 X gaming headset in Mars Red."),
    draw("THX", "THX Black Friday gaming headset giveaway",
         "https://gleam.io/xLqmg/black-friday-giveaway-with-thx-partners", "2026-12-02T07:59:00Z",
         "gaming audio gear from Razer, Edifier Hecate, QCY, or Hator.", eligibility="US only.",
         source_url="https://www.thx.com/blog/gaming-guide-to-hear-the-holidays-thx-spatial-audio-must-have-gifts-and-deals/"),
    draw("AGON by AOC", "AOC AGON PRO Counter-Strike 2 gaming monitor giveaway",
         "https://gleam.io/giveaways/qnBYN", "2026-11-24T07:59:00Z",
         "one of ten 610 Hz AGON PRO CS24A monitors. The official rules exclude Québec.",
         eligibility="Open to residents of the United States and Canada."),
    draw("Razer", "Razer and BLACKWOOD game key giveaway",
         "https://gleam.io/giveaways/EMVCt", "2026-11-21T07:59:00Z",
         "one of twenty BLACKWOOD game keys, split between the base game and Supporter Edition."),
    draw("That Bald Gamer", "Nintendo Switch 2 and Zelda giveaway",
         "https://gleam.io/giveaways/i17bw", "2026-11-25T05:00:00Z",
         "a Nintendo Switch 2 console and a physical copy of Ocarina of Time. The organizer offers international shipping.",
         eligibility="See the entry rules."),
)


def current_campaigns(now: datetime) -> list[RawItem]:
    return [offer for offer in CAMPAIGNS
            if (not offer.published_at or offer.published_at <= now) and now < offer.expires_at]
