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


def _sample(dimension) -> list:
    """A few options to judge a dimension by. TOTAL says nothing, so it goes."""
    return [o for o in dimension.options
            if (o.label or "").strip().upper() != "TOTAL"][:_SIRUTA_SAMPLE]


def _most(options, holds) -> bool:
    """True when more than half the sampled options satisfy the predicate."""
    if not options:
        return False
    return sum(1 for o in options if holds(o.label)) * 2 > len(options)


def _is_settlement(label: str) -> bool:
    """A name that says what kind of settlement it is: MUNICIPIUL, ORAS,
    SECTORUL. Communes carry no prefix, so they do not count as evidence here;
    this is a test for proof, not a census."""
    return parse_territory(label)[2] in ("municipiu", "oras", "sector")


def _is_administrative(label: str) -> bool:
    """A name from the county and region nomenclator."""
    return option_level(label) in ("judet", "macroregiune", "regiune")


def names_places(dimension) -> bool:
    """Do the options themselves name places?

    The last resort when neither details nor the label give it away. GOS102A
    calls its locality dimension 'Municipii si orase', which mentions neither
    counties nor localities; if details were silent too, the options would be
    the only evidence left, and they are good evidence. A settlement type or a
    county name is not something a dimension of ages or of CAEN activities
    carries by accident, which a numeric prefix on its own would be: '0 ani'
    starts with a number the same way '1017 MUNICIPIUL ALBA IULIA' does.
    """
    options = _sample(dimension)
    return _most(options, lambda lab: _is_settlement(lab) or _is_administrative(lab))


def names_settlements(dimension) -> bool:
    """Do most options name settlements, whatever the dimension is called?"""
    return _most(_sample(dimension), _is_settlement)


def is_territorial(dimension, details: dict) -> bool:
    """True if the dimension is territorial.

    Three routes, in order of how much they can be trusted: details says so,
    the label says so, or the options themselves name places.
    """
    if dimension.dim_code in _territory_dimcodes(details):
        return True
    lab = _norm(dimension.label)
    if any(k in lab for k in _LABEL_HINTS):
        return True
    return names_places(dimension)


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
    """Assign d.role, and for territorial ones d.finest_level, in place.

    Order matters: territory, time, caen, unit of measure, then other.

    The role says what a dimension is; for a territorial one that is not
    enough, because 'teritoriu' covers both a county dimension and a locality
    one. d.finest_level is the sub sign: the finest real level the dimension
    reaches, so asking which dimension holds the localities never has to go
    through the label. It is 'necunoscut' for territorial names outside the
    nomenclator, and empty for everything that is not territorial.
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
        d.finest_level = (
            finest_level(dimension_levels(d, details)) or "necunoscut"
        ) if d.role == "teritoriu" else ""


def finest_level(levels) -> str | None:
    """The finest REAL level in a set of levels, coarse to fine.

    'necunoscut' is not a level to ask for: names that do not fit the
    nomenclator do not form a useful slice. None when there is no real one.
    """
    present = set(levels or ())
    real = [lv for lv in _LEVEL_ORDER
            if lv in present and lv != "necunoscut"]
    return real[-1] if real else None


def _looks_like_siruta(dimension) -> bool:
    """Do most options carry a numeric SIRUTA prefix?

    We only look at a sample: this is a confirmation, not a census.
    """
    return _most(_sample(dimension),
                 lambda lab: siruta_from_label(lab) is not None)


def is_locality_dimension(dimension, details: dict) -> bool:
    """True if the dimension really holds localities.

    details.nomLoc is the authoritative INS signal and is taken as such. The
    label alone is not enough: TMP1173 has a dimension called 'Statii de
    monitorizare de tip fond urban - Localitate' whose options are monitoring
    stations, not localities. So the label needs confirmation, either from
    matSiruta or from numeric prefixes on the options.

    A label that never mentions localities at all is the GOS102A case,
    'Municipii si orase'. There the options have to carry both a SIRUTA code
    and a settlement type, which together no other kind of dimension does.
    """
    if dimension.dim_code == details.get("nomLoc"):
        return True
    if not is_territorial(dimension, details):
        return False
    if "localit" in _norm(dimension.label):
        return bool(details.get("matSiruta")) or _looks_like_siruta(dimension)
    return _looks_like_siruta(dimension) and names_settlements(dimension)


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


def derived_keys(dimension) -> list[str]:
    """Which derived columns this dimension's options justify, in order.

    The same rule parse.standardize applies, read off the options instead of
    the rows: a column is worth adding only when something in it is not empty,
    so a county dimension gets 'nivel' alone while a locality one gets all
    four. It is what territory_columns() names the columns from.

    One honest difference: standardize decides on the rows that came back, so a
    download filtered down to aggregates alone will not carry the SIRUTA column
    even though the dimension could have.
    """
    parsed = [parse_territory(str(o.label)) for o in dimension.options]
    originals = [str(o.label).strip() for o in dimension.options]

    keys = []
    if any(p[0] is not None for p in parsed):
        keys.append("siruta")
    keys.append("nivel")                      # always worth having
    if any(p[2] is not None for p in parsed):
        keys.append("tip")
    if any(p[3] != o for p, o in zip(parsed, originals)):
        keys.append("nume")
    return keys


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
