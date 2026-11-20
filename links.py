"""Extract and normalize destinations without following untrusted URLs."""
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import EPIC_ANDROID, EPIC_IOS, SOURCE_HOSTS, WIDGET_HOSTS

URL_RE = re.compile(r"https?://[^\s<>\x22\x27\[\]]+", re.I)
DOMAIN_RE = re.compile(r"(?:www\.)?(?:" + "|".join(map(re.escape, WIDGET_HOSTS)) + r")/", re.I)
HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
TRACKING = {
    "ref", "referrer", "referral", "referer", "affiliate", "aff", "affid",
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "dclid", "igshid",
    "mc_cid", "mc_eid", "_ga", "si", "snr", "utm", "mkt_tok",
}


def clean_url(url: str, *, canonical: bool = False) -> str:
    value = html.unescape(url).strip()
    if not value or len(value) > 2048 or re.search(r"[\\\s\x00-\x1f\x7f]", value):
        return ""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").rstrip(".").lower().encode("idna").decode()
        port = parts.port
        query = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=100)
    except (ValueError, UnicodeError):
        return ""
    if (parts.scheme not in {"http", "https"} or not HOST_RE.fullmatch(host)
            or parts.username is not None or port not in {None, 80 if parts.scheme == "http" else 443}
            or host.endswith((".local", ".localhost", ".internal", ".test", ".invalid", ".onion"))):
        return ""
    known_host = host.removeprefix("www.")
    if not canonical:
        return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, parts.fragment))
    path = parts.path.rstrip("/") or "/"
    scheme = "https" if known_host in SOURCE_HOSTS else parts.scheme
    ignored = {
        "store.steampowered.com": {"l", "cc"}, "store.epicgames.com": {"lang"}, "gog.com": {"locale"},
        "gleam.io": {"gsr"},
    }.get(known_host, set())
    query = [(key, val) for key, val in query
             if key.casefold() not in TRACKING | ignored and not key.lower().startswith("utm_")]
    fragment = parts.fragment
    query.sort()
    if known_host in SOURCE_HOSTS:
        host = known_host
    # These campaign/product IDs stay stable when the display slug changes.
    patterns = {
        "gleam.io": r"^/(?:giveaways/)?([a-zA-Z0-9]{5,8})(?:/.*)?$",
        "kingsumo.com": r"^(/g/[a-zA-Z0-9]+)(?:/.*)?$",
        "store.steampowered.com": r"^(/(?:app|sub|bundle)/\d+)(?:/.*)?$",
        "store.epicgames.com": r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?(p/[^/]+)$",
        "gog.com": r"^/(?:[a-z]{2}/)?(game/[^/]+)$",
    }
    match = re.match(patterns.get(host, r"(?!)"), path, re.I)
    if match:
        path = "/" + match[1].lstrip("/")
    # Preserve fragment-only routing on third-party pages.
    if not fragment.startswith(("/", "!/")) or known_host in SOURCE_HOSTS:
        fragment = ""
    return urlunsplit((scheme, host, path, urlencode(query), fragment))


def platform_for(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    if host == "store.epicgames.com":
        if mobile := re.search(r"/p/[^/]+-(android|ios)-[a-f0-9]{6}/?$", parts.path):
            return EPIC_ANDROID if mobile[1] == "android" else EPIC_IOS
    return SOURCE_HOSTS.get(host, "itch.io" if host.endswith(".itch.io") else "")


def destination_rank(url: str) -> int:
    host, path = urlsplit(url).hostname or "", urlsplit(url).path
    base = host.removeprefix("www.")
    if base in WIDGET_HOSTS and path.strip("/"):
        return 3
    if platform_for(url) and path.strip("/"):
        return 2
    if host == "reddit.com" or host.endswith(".reddit.com") or base in {"youtu.be", "youtube.com"}:
        return 0
    return 1


def extract_links(text: str) -> list[str]:
    text = html.unescape(text.replace(r"\/", "/"))
    urls = list(URL_RE.finditer(text))
    result = []
    for match in urls:
        candidate = match[0].rstrip(".,;:!?")
        while candidate.endswith(")") and candidate.count(")") > candidate.count("("):
            candidate = candidate[:-1]
        result.append(clean_url(candidate))
    for match in DOMAIN_RE.finditer(text):
        # A bare domain embedded inside a different URL isn't a destination.
        if any(url.start() <= match.start() < url.end() for url in urls):
            continue
        if match.start() and re.match(r"[\w./@-]", text[match.start() - 1]):
            continue
        bare = re.match(r"[^\s<>\x22\x27\[\]()]+", text[match.start():])
        if bare:
            result.append(clean_url("https://" + bare[0].rstrip(".,;:!?")))
    return list(dict.fromkeys(url for url in result if url))
