"""Parse explicit offer dates without treating publication dates as deadlines."""
import re
from datetime import UTC, datetime, time, timedelta, timezone

from dateutil.parser import parse

MONTH_GROUPS = (
    "january jan enero janeiro januar janvier janv",
    "february feb febrero fevereiro februar f[eé]vrier f[eé]vr",
    "march mar marzo mar[cç]o m[aä]rz mars",
    "april apr abril avr avril",
    "may mayo maio mai",
    "june jun junio junho juni juin",
    "july jul julio julho juli juillet",
    "august aug agosto ao[uû]t",
    "september sep sept septiembre setembro septembre",
    "october oct octubre outubro oktober octobre okt",
    "november nov noviembre novembro novembre",
    "december dec diciembre dezembro dezember d[eé]cembre d[eé]c dez",
)
MONTH = r"(?:" + "|".join("|".join(group.split()) for group in MONTH_GROUPS) + r")\.?"
YEAR = r"\d{4}"
CLOCK = r"(?:[T ]\s*\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*[ap]m)?(?:\s*(?:[+-]\d{2}:?\d{2}|Z|UTC|GMT|[ECMP][SD]T|CE[ST]T?))?)?"
FULL_DATE = (
    rf"(?:{YEAR}-\d{{2}}-\d{{2}}|\d{{1,2}}[./-]\d{{1,2}}(?:[./-]{YEAR})?|"
    rf"\d{{1,2}}(?:st|nd|rd|th|er)?\s+(?:de\s+)?{MONTH}(?:,?\s+(?:de\s+)?{YEAR})?|"
    rf"{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th|er)?(?:,?\s+{YEAR})?){CLOCK}"
)
DEADLINE = re.compile(
    rf"\b(?:ends?|ending|expires?|deadline|entry closes?|closing date|end date|claim (?:it )?by|valid until|"
    rf"available until|hasta|vence|termina|finaliza|jusqu['’]au|se termine|date limite|"
    rf"endet|g[uü]ltig bis|teilnahmeschluss|at[eé]|encerra)\b"
    rf"\s*(?::|–|—|-)?\s*(?:(?:on|at|the|am|el|le|em|bis)\s+){{0,2}}({FULL_DATE})(?![\d\w])",
    re.I,
)
TZINFOS = {name: timezone(timedelta(hours=offset)) for name, offset in {
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7, "CET": 1, "CEST": 2,
}.items()}


def parse_date(value: str, now: datetime, language: str = "", *, deadline: bool = False) -> datetime | None:
    if not value or value.upper() in {"N/A", "NONE"}:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        for group in MONTH_GROUPS:
            original, *aliases = group.split()
            if aliases:
                value = re.sub(r"\b(?:" + "|".join(aliases) + r")\b\.?", original, value, flags=re.I)
        value = re.sub(r"\s+de\s+|(?<=\d)er\b", lambda match: " " if match[0].startswith(" ") else "", value)
        try:
            parsed = parse(
                value, default=datetime(now.year, 1, 1), tzinfos=TZINFOS,
                dayfirst=language in {"es", "pt", "de", "fr"},
            )
        except (ValueError, OverflowError):
            return None
        if deadline and not re.search(r"\b\d{4}\b", value) and parsed.date() < now.date() - timedelta(days=180):
            parsed = parsed.replace(year=now.year + 1)
    if deadline and not re.search(r"\d:\d\d", value):
        parsed = datetime.combine(parsed.date(), time(23, 59, 59), parsed.tzinfo)
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def ending_date(text: str, now: datetime, language: str = "") -> datetime | None:
    candidates = []
    for match in DEADLINE.finditer(text):
        date = parse_date(match[1], now, language, deadline=True)
        if date is not None:
            candidates.append(date)
    return min(candidates, default=None)
