"""Dimension roles and territorial levels.

A dimension is territorial if the details block says so OR if its label says so.
Both routes are needed: matrices built on the county plus locality nomenclator
(FOM104D) are marked in details, but the common case is a single hierarchical
dimension holding macroregion, region and county together, and there the
details key is sometimes missing.

An option's level is read from its name: TOTAL is national, MACROREGIUNEA is a
macroregion, REGIUNEA is a region, and a county is a name that appears in the
actual list of Romanian counties. Anything else is unknown, on purpose.

Note: details.matMaxDim is the number of dimensions, not a cell limit.
"""
import difflib
import re
from typing import Literal

_TERRITORY_KEYS = ("nomJud", "nomLoc", "matRegJ")

# coarse to fine; 'necunoscut' sits at the end, for territorial names that do
# not fit the administrative nomenclator
_LEVEL_ORDER = ("national", "macroregiune", "regiune", "judet", "localitate",
                "necunoscut")

# the same thing as a type, so editors suggest the values as you type.
# A test keeps the Literal and the tuple in sync.
Level = Literal["national", "macroregiune", "regiune", "judet", "localitate",
                "necunoscut"]

# the 42 counties plus the Bucharest variants found in INS data, normalized.
# Without this list any unrecognized territorial name fell through to 'judet',
# and the monitoring stations of an environment indicator came out as counties.
_COUNTIES = frozenset((
    "alba", "arad", "arges", "bacau",
    "bihor", "bistrita-nasaud", "botosani", "braila",
    "brasov", "buzau", "calarasi", "caras-severin",
    "cluj", "constanta", "covasna", "dambovita",
    "dolj", "galati", "giurgiu", "gorj",
    "harghita", "hunedoara", "ialomita", "iasi",
    "ilfov", "maramures", "mehedinti", "mun. bucuresti -incl. sai",
    "municipiul bucuresti", "mures", "neamt", "olt",
    "prahova", "salaj", "satu mare", "sibiu",
    "suceava", "teleorman", "timis", "tulcea",
    "valcea", "vaslui", "vrancea",
))

# the national total is not always spelled 'TOTAL'; some AMIGO and CON matrices
# call it 'Nivel National'
_NATIONAL_LABELS = frozenset(("nivel national", "total national"))

# how many options we sample to decide whether a dimension really holds
# localities
_SIRUTA_SAMPLE = 20

# words that give away a territorial dimension when details is silent
_LABEL_HINTS = ("judet", "localit", "macroregiun", "regiun")


def level_error(name, available, cod: str | None = None) -> ValueError:
    """The error for an invalid level: what is possible, plus what you likely meant.

    The same shape of message in search and in get; only the list of possible
    values differs, because for one indicator its own levels are what matter.
    """
    available = list(available)
    where_part = f" for {cod}" if cod else ""
    message = (f"unknown level {name!r}{where_part}. "
             f"Available: {', '.join(available) or 'none'}.")
    closest = difflib.get_close_matches(str(name).lower(), available, n=1)
    if closest:
        message += f" Did you mean {closest[0]!r}?"
    return ValueError(message)


def _norm(s: str) -> str:
    """Lowercase and strip diacritics, so 'județe' matches 'judete'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return (s or "").lower().translate(repl)


def option_level(label: str) -> str:
    """The level of a territorial option, from its name.

    Aggregates are recognized by prefix. A county is recognized by membership in
    the real nomenclator, not as a fallback: otherwise every unknown territorial
    name, from monitoring stations to border crossing points, would have come
    out as a county.
    """
    text = (label or "").strip()
    u = text.upper()
    if u.startswith("TOTAL") or _norm(text) in _NATIONAL_LABELS:
        return "national"
    if u.startswith("MACROREGIUNEA"):
        return "macroregiune"
    if u.startswith("REGIUNEA"):
        return "regiune"
    if _norm(text) in _COUNTIES:
        return "judet"
    return "necunoscut"


def _territory_dimcodes(details: dict) -> set:
    """The dimCodes marked territorial in details. A value of 0 does not count."""
    return {details[k] for k in _TERRITORY_KEYS if details.get(k)}


def is_territorial(dimension, details: dict) -> bool:
    """True if the dimension is territorial, from details or from its label."""
    if dimension.dim_code in _territory_dimcodes(details):
        return True
    lab = _norm(dimension.label)
    return any(k in lab for k in _LABEL_HINTS)


def is_caen(dimension, details: dict) -> bool:
    """True if the dimension is a CAEN classification, from details or label.

    Symmetric with is_territorial: INS does not always flag CAEN in details.
    FOM104F has matCaen1 and matCaen2 at 0 even though it carries a dimension
    called 'CAEN Rev.2 (activitati ale economiei nationale)'.
    """
    codes_wanted = {details.get("matCaen1"), details.get("matCaen2")} - {0, None}
    if dimension.dim_code in codes_wanted:
        return True
    return "caen" in _norm(dimension.label)


def assign_roles(dimensions: list, details: dict) -> None:
    """Assign d.role to every dimension, in place.

    Order matters: territory, time, caen, unit of measure, then other.
    """
    time_code = details.get("matTime")
    for d in dimensions:
        if is_territorial(d, details):
            d.role = "teritoriu"
        elif time_code and d.dim_code == time_code:
            d.role = "timp"
        elif is_caen(d, details):
            d.role = "caen"
        elif d.label.strip().lower().startswith("um:"):
            d.role = "um"
        else:
            d.role = "alt"


def _looks_like_siruta(dimension) -> bool:
    """Do most options carry a numeric SIRUTA prefix?

    We only look at a sample: this is a confirmation, not a census.
    """
    options = [o for o in dimension.options
               if (o.label or "").strip().upper() != "TOTAL"][:_SIRUTA_SAMPLE]
    if not options:
        return False
    with_code = sum(1 for o in options if siruta_from_label(o.label) is not None)
    return with_code * 2 > len(options)


def is_locality_dimension(dimension, details: dict) -> bool:
    """True if the dimension really holds localities.

    details.nomLoc is the authoritative INS signal and is taken as such. The
    label alone is not enough: TMP1173 has a dimension called 'Statii de
    monitorizare de tip fond urban - Localitate' whose options are monitoring
    stations, not localities. So the label needs confirmation, either from
    matSiruta or from numeric prefixes on the options.
    """
    if dimension.dim_code == details.get("nomLoc"):
        return True
    if "localit" not in _norm(dimension.label):
        return False
    return bool(details.get("matSiruta")) or _looks_like_siruta(dimension)


def dimension_levels(dimension, details: dict) -> set:
    """The levels covered by a single dimension.

    A confirmed locality dimension reports 'localitate' directly. One that
    merely carries the word in its label, without confirmation, reports the
    levels of its options, which for monitoring stations means 'necunoscut'.
    """
    if not is_territorial(dimension, details):
        return set()
    if is_locality_dimension(dimension, details):
        return {"localitate"}
    return {option_level(o.label) for o in dimension.options}


def levels_present(dimensions: list, details: dict) -> list[str]:
    """The matrix's territorial levels, from coarse to fine."""
    found = set()
    for d in dimensions:
        found |= dimension_levels(d, details)
    return [x for x in _LEVEL_ORDER if x in found]


# type prefixes found in locality names, longest first
_TYPE_PREFIXES = (
    ("MUNICIPIUL", "municipiu"),
    ("ORASUL", "oras"),
    ("ORAS", "oras"),
    ("SECTORUL", "sector"),
    ("SECTOR", "sector"),
    ("COMUNA", "comuna"),
)

_LEADING_CODE = re.compile(r"^(\d+)\s+(.*)$")


def parse_territory(label: str) -> tuple:
    """Break a territorial name into (siruta, level, type, name).

    Localities arrive as 'SIRUTA TYPE NAME': '1017 MUNICIPIUL ALBA IULIA',
    '1151 ORAS ABRUD'. Communes carry no type prefix: '2130 ALBAC'.
    Aggregates and counties have no SIRUTA at all: 'TOTAL',
    'MACROREGIUNEA UNU', 'Regiunea NORD-VEST', 'Cluj'.
    """
    text = (label or "").strip()
    m = _LEADING_CODE.match(text)
    if not m:
        return (None, option_level(text), None, text)

    siruta = int(m.group(1))
    rest = m.group(2).strip()
    upper = rest.upper()
    for prefix, tip in _TYPE_PREFIXES:
        if upper.startswith(prefix + " "):
            return (siruta, "localitate", tip, rest[len(prefix):].strip())
    # communes carry no type prefix
    return (siruta, "localitate", "comuna", rest)


def siruta_from_label(label: str) -> int | None:
    """The SIRUTA code, the numeric prefix of a locality name.

    '1017 MUNICIPIUL ALBA IULIA' gives 1017. None when the label does not start
    with digits, as in 'TOTAL'. Present when details.matSiruta is set.
    """
    if not label:
        return None
    head = label.split(maxsplit=1)[0]
    return int(head) if head.isdigit() else None


def group_localities_by_county(locality_dimension) -> dict:
    """Group locality options by county, through parent_id.

    A locality's parent_id is the county's nomItemId. This is the basis of the
    county by county chunking used for locality level matrices.
    """
    groups = {}
    for opt in locality_dimension.options:
        groups.setdefault(opt.parent_id, []).append(opt)
    return groups
