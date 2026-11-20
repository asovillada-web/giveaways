"""Sources and vocabulary. Add regular expressions using case-insensitive text."""
from dataclasses import dataclass


SUBREDDITS = ("giveaways", "FreeGameFindings", "freegames", "SteamGiveaway", "pcmasterrace")
WIDGET_HOSTS = ("gleam.io", "sweepwidget.com", "kingsumo.com", "rafflecopter.com")
SOURCE_HOSTS = {
    **dict(zip(WIDGET_HOSTS, ("Gleam", "SweepWidget", "KingSumo", "Rafflecopter"))),
    "store.steampowered.com": "Steam",
    "steamcommunity.com": "Steam",
    "store.epicgames.com": "Epic Games",
    "gog.com": "GOG",
    "itch.io": "itch.io",
    "gamerpower.com": "GamerPower",
}
METADATA_HOSTS = frozenset((*WIDGET_HOSTS, "store.steampowered.com", "store.epicgames.com", "gog.com"))

GIVEAWAY = (
    r"\b(?:give[ -]?aways?|sweepstakes?|raffle[sd]?|freebie[s]?|free(?: to keep| (?:games?|dlc|keys?|software))?"
    r"|sorteios?|sorteos?|gewinnspiel\w*|verlosung\w*|concours|tirage au sort|gratuits?|gratuita?s?|kostenlos\w*)\b"
)
HARDWARE = (
    r"\b(?:[rg]tx(?:\s?\d{3,4})?|rx\s?\d{3,4}|gpu[s]?|radeon|geforce|graphics card[s]?|"
    r"tarjeta[s]? gr[aá]fica[s]?|placa[s]? de v[ií]deo|grafikkarte[n]?|carte[s]? graphique[s]?|"
    r"ps[45]|playstation(?:\s?[45])?|xbox(?: series [sx])?|(?:nintendo )?switch(?:\s?2)?|"
    r"steam deck|consoles?|laptops?|notebooks?|macbook|chromebook|ordenador port[aá]til|ordinateur portable|"
    r"gaming pc|pc gamer|pc build|mini[ -]?pc|prebuilt|desktop pc|computador|"
    r"smartphones?|cell phones?|phone[s]?|iphone[s]?|android phone|celular(?:es)?|"
    r"prozessors?|processors?|ryzen|ssd[s]?|cpus?|motherboards?|tablets?|ipad)\b"
)
GEAR = (
    r"\b(?:keyboards?|teclados?|tastatur\w*|claviers?|gaming mice|mice|mouse|souris|"
    r"headsets?|headphones?|auriculares|fone[s]? de ouvido|kopfh[oö]rer|casques?|"
    r"monitors?|monitor[eé]s?|bildschirm\w*|[eé]crans?|controllers?|mandos?|manettes?|gamepads?|"
    r"microphones?|webcams?|mousepads?|gaming chairs?)\b"
)
DIGITAL = (
    r"\b(?:steam|epic games|gog|itch\.io|pc|gaming|video[ -]?games?|games?|juegos?|jogos?|jeux?|"
    r"videospiel\w*|spiel\w*|dlc|skins?|game keys?|software|license keys?|game pass|"
    r"gift cards?|store credit|tarjeta[s]? regalo|cartes? cadeaux?|gutscheine?|vale[ -]?presente|"
    r"psn|playstation store|nintendo eshop|ubisoft|prime gaming|free keys?|jogo|origin)\b"
)
BLOCKLIST = (
    r"\b(?:crypto(?:currency)?|bitcoin|memecoins?|nfts?|cash\s?app|venmo|cash flip|casino|"
    r"betting|makeup|beauty products?|skincare|skin care|cosmetics?|perfume|weight loss)\b"
)
FREE_CLAIM = (
    r"\b(?:free to keep|free forever|free for everyone|keep it forever|100\s*%\s*(?:free|gratis|gratuit)|"
    r"free (?:game|dlc|software|key|license)|claim (?:it |\w+ ){0,5}for free|get (?:it |\w+ ){0,5}for free|"
    r"(?:claim|redeem|grab) (?:your |a )?(?:free )?(?:copy|key)|"
    r"gratis para siempre|gr[aá]tis para sempre|kostenlos behalten|gratuit [àa] vie)\b"
)
CHANCE = (
    r"\b(?:win (?:a |an )?|drawing|chance to win|random(?:ly selected)? winner|winners? (?:will|chosen|announced)|"
    r"enter (?:for a chance|to win)|sweepstakes?|raffles?|contest|"
    r"para ganar|ganadores?|ganhadores?|sorteio|gewinnspiel|verlosung|concours|tirage au sort)\b"
)
NOT_FREE = (
    r"\b(?:free[ -]to[ -]play|free weekend|free trial|play for free|trial period|"
    r"temporarily free to play|free with (?:purchase|subscription)|(?:requires|with)\s+(?:a |an )?(?:paid |active )?subscription|"
    r"for (?:prime|plus|game pass) members|prime (?:gaming|members)|playstation plus|game pass ultimate|"
    r"compra obligatoria|kostenlose testversion|essai gratuit)\b"
)


@dataclass(frozen=True)
class Directory:
    kind: str
    url: str
    name: str
    item_selector: str = ""
    title_selector: str = ""
    description_selector: str = ""
    link_selector: str = ""
    # A platform hint may help classify titles that contain only a product name.
    platform: str = ""
    guaranteed: bool = False
    source_type: str = "Community"


DIRECTORIES = (
    Directory("gamerpower", "https://www.gamerpower.com/api/giveaways", "GamerPower"),
    Directory("rss", "https://www.gamerpower.com/rss/giveaways", "GamerPower"),
    # RSS/Atom and public HTML listings use the same pipeline. Example configuration:
    # Directory("rss", "https://publisher.example/promotions.xml", "Publisher", platform="Steam"),
    # Directory("html", "https://publisher.example/promotions", "Publisher",
    #           item_selector="article", title_selector="h2", description_selector="p",
    #           link_selector="a.claim", platform="Steam"),
)
