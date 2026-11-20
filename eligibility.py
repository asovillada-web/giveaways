"""Extract eligibility statements. Locale hints belong to the source, not these rules."""
import re
from dataclasses import dataclass

REGIONS = {
    "NA": r"north america|am[eé]rica del norte|am[eé]rica do norte|nordamerika|am[eé]rique du nord|NA",
    "EU": r"european union|uni[oó]n europea|uni[aã]o europeia|union europ[eé]enne|europ[aä]ische union|EU",
    "EUROPE": r"europe|europa",
    "LATAM": r"latin america|lat[aá]m|am[eé]rica latina|lateinamerika|am[eé]rique latine",
    "APAC": r"asia[ -]pacific|apac",
    "US": r"united states(?: of america)?|estados unidos|[ée]tats-unis|vereinigte staaten|EE\.?\s?UU\.?|U\.?S\.?A?\.?",
    "GB": r"united kingdom|great britain|british|reino unido|royaume-uni|vereinigtes k[oö]nigreich|U\.?K\.?|GB",
    "CA": r"canada|canadian[s]?|canad[aá]|canadiens?|kanada|CA",
    "PR": r"puerto rico|PR",
    "AU": r"australia|australian[s]?|austr[aá]lie|australien|AU",
    "NZ": r"new zealand|nueva zelanda|nouvelle-z[eé]lande|neuseeland|NZ",
    "DE": r"germany|german[s]?|deutschland|allemagne|alemania|alemanha|DE",
    "FR": r"france|french|fran[cç]a|francia|frankreich|FR",
    "ES": r"spain|spanish|espa[nñ]a|espagne|spanien|ES",
    "PT": r"portugal|PT",
    "BR": r"brazil|brazilian[s]?|brasil|br[eé]sil|brasilien|BR",
    "MX": r"mexico|mexican[s]?|m[eé]xico|mexique|mexiko|MX",
    "CO": r"colombia|colombian[s]?|colombie|kolumbien|CO",
    "AR": r"argentina|argentine|argentinien|AR",
    "CL": r"chile|chili|CL",
    "IN": r"india|indien|inde|IN",
    "JP": r"japan|jap[oó]n|jap[aã]o|japon|JP",
    "CN": r"china|chine|CN",
    "KR": r"south korea|cor[eé]e du sud|cor[eé]ia do sul|corea del sur|s[uü]dkorea|KR",
    "PH": r"philippines|filipinas|PH",
    "TW": r"taiwan|ta[iï]wan|TW",
    "VN": r"viet\s?nam|VN",
    "ID": r"indonesia|indon[eé]sie|indonesien|ID",
    "SG": r"singapore|singapur|singapour|singapura|SG",
    "MY": r"malaysia|malaisie|malasia|MY",
    "IT": r"italy|italia|italie|italien|IT",
    "NL": r"netherlands|pa[ií]ses bajos|pa[ií]ses baixos|pays-bas|niederlande|NL",
    "BE": r"belgium|belgique|b[eé]lgica|belgien|BE",
    "CH": r"switzerland|suisse|schweiz|suiza|su[ií][cç]a|CH",
    "AT": r"austria|autriche|[oö]sterreich|AT",
    "CZ": r"czech republic|czechia|tch[eé]quie|tschechien|CZ",
    "GR": r"greece|gr[eè]ce|griechenland|GR",
    "HU": r"hungary|hongrie|ungarn|HU",
    "IE": r"ireland|irlande|irland|irlanda|IE",
    "PL": r"poland|pologne|polen|polonia|PL",
    "SE": r"sweden|su[eè]de|schweden|suecia|su[eé]cia|SE",
    "NO": r"norway|norv[eè]ge|norwegen|noruega|NO",
    "DK": r"denmark|danemark|d[aä]nemark|dinamarca|DK",
    "FI": r"finland|finlande|finnland|finlandia|FI",
    "RU": r"russia|russie|russland|rusia|r[uú]ssia|RU",
    "UA": r"ukraine|ucrania|ucr[aâ]nia|UA",
    "ZA": r"south africa|afrique du sud|s[uü]dafrika|sud[aá]frica|[aá]frica do sul|ZA",
    "NG": r"nigeria|nig[eé]ria|NG",
    "AE": r"united arab emirates|UAE|AE",
    "TR": r"turkey|t[uü]rkiye|t[uú]rkei|turqu[ií]a|turquia|turquie|TR",
}
REGION_RE = {
    code: re.compile(r"(?<!\w)(?:" + terms + r")(?!\w)", re.I)
    for code, terms in REGIONS.items()
}
GLOBAL = re.compile(
    r"\b(?:world[ -]?wide|global(?:ly)?|international\w*|all countries|open to everyone|"
    r"todo el mundo|mundial(?:mente)?|mundo inteiro|weltweit|alle l[aä]nder|monde entier)\b", re.I
)
CUE = re.compile(
    r"\b(?:only|eligible|eligibility|residents?|residency|open to|available (?:in|to)|restricted|"
    r"restricted to|valid in|ships? to|shipping to|exclusive(?:ly)?|s[oó]lo|solamente|exclusiv\w*|"
    r"apenas|somente|dispon[ií]vel em|disponible (?:en|au)|r[eé]serv[eé] aux|nur|teilnahme|offen f[uü]r)\b", re.I
)
EXCLUDE = re.compile(
    r"\b(?:except(?:ing)?|exclud(?:es?|ing)|unavailable in|not (?:open to|available in|eligible in)|"
    r"sauf|except[oé]|exceto|au[sß]er|sin incluir|excluding)\b", re.I
)
RESTRICTION = re.compile(r"\b(?:only (?:open |available )?to residents|only residents|residents? of|shipping restricted|selected countries|participating (?:countries|regions)|region[ -]locked|not worldwide|geo[ -]?restricted)\b", re.I)
BOUNDARY = re.compile(r"[\n!?;]|(?<!\.[A-Z])\.\s+|\s+\|\s+")


@dataclass(frozen=True)
class Eligibility:
    scope: str = "Unspecified"
    worldwide: bool = True
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    evidence: int = 0


def codes_in(text: str) -> set[str]:
    return {
        code for code, pattern in REGION_RE.items()
        if any(len(match[0]) > 2 or match[0].isupper() for match in pattern.finditer(text))
    }


def parse_region(text: str) -> Eligibility:
    restrict, exclude = set(), set()
    global_scope, generic = False, False
    for note in re.findall(r"\(([^()\n]{1,100})\)", text):
        if EXCLUDE.match(note):
            exclude.update(codes_in(EXCLUDE.split(note, maxsplit=1)[1]))
            text = text.replace(f"({note})", "")
    for statement in BOUNDARY.split(text):
        statement = statement.strip()
        if not statement:
            continue
        parts = EXCLUDE.split(statement, maxsplit=1)
        base = parts[0]
        codes = codes_in(base)
        match = GLOBAL.search(base)
        if match and not re.search(r"(?:\bnot|\bno|\bpas)\s+(?:open\s+)?$", base[:match.start()], re.I):
            global_scope = True
        # Standalone tags like [US] and (EU / UK) supply eligibility directly.
        tags = set()
        for tag in re.findall(r"\[([^\]]{1,60})\]|\(([^)]{1,60})\)", base):
            label = next(value for value in tag if value)
            if re.fullmatch(r"[A-Z]{2,6}(?:\s*[/,+&]\s*[A-Z]{2,6})*", label):
                tags.update(codes_in(label))
        if CUE.search(base) or re.fullmatch(r"[A-Z]{2,6}(?:\s*[/,+&]\s*[A-Z]{2,6})*", base):
            restrict.update(codes)
        restrict.update(tags)
        if RESTRICTION.search(base):
            generic = True
        if len(parts) > 1:
            exclude.update(codes_in(parts[1]))
    if restrict:
        return Eligibility(" / ".join(sorted(restrict)), False, tuple(sorted(restrict)),
                           tuple(sorted(exclude)), 3)
    if exclude:
        return Eligibility("Worldwide except " + " / ".join(sorted(exclude)), False, (), tuple(sorted(exclude)), 3)
    if generic:
        return Eligibility("Restricted", False, evidence=2)
    if global_scope:
        return Eligibility("Worldwide", True, evidence=1)
    return Eligibility()
