"""Rolurile dimensiunilor și nivelele teritoriale.

O dimensiune e teritorială dacă o spune details SAU dacă o spune label-ul.
Ambele căi sunt necesare: matricele cu nomenclator de județe plus localități
(FOM104D) se recunosc din details, dar cazul obișnuit e o singură dimensiune
ierarhică, cu macroregiune, regiune și județ la un loc, iar acolo cheia din
details lipsește uneori.

Nivelul unei opțiuni se citește din prefixul denumirii: TOTAL e national,
MACROREGIUNEA e macroregiune, REGIUNEA e regiune, restul sunt județe.

Atenție: details.matMaxDim e numărul de dimensiuni, nu o limită de celule.
"""
import re

_TERRITORY_KEYS = ("nomJud", "nomLoc", "matRegJ")

# de la general la specific
_LEVEL_ORDER = ("national", "macroregiune", "regiune", "judet", "localitate")

# cuvinte care tradeaza o dimensiune teritoriala cand details tace
_LABEL_HINTS = ("judet", "localit", "macroregiun", "regiun")


def _norm(s: str) -> str:
    """Minuscule, fără diacritice, ca 'județe' să prindă 'judete'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return (s or "").lower().translate(repl)


def option_level(label: str) -> str:
    """Nivelul unei opțiuni teritoriale, după prefixul denumirii."""
    u = (label or "").strip().upper()
    if u.startswith("TOTAL"):
        return "national"
    if u.startswith("MACROREGIUNEA"):
        return "macroregiune"
    if u.startswith("REGIUNEA"):
        return "regiune"
    return "judet"


def _territory_dimcodes(details: dict) -> set:
    """dimCode-urile marcate teritorial în details. Valorile 0 nu contează."""
    return {details[k] for k in _TERRITORY_KEYS if details.get(k)}


def is_territorial(dimension, details: dict) -> bool:
    """True dacă dimensiunea e teritorială, din details sau din label."""
    if dimension.dim_code in _territory_dimcodes(details):
        return True
    lab = _norm(dimension.label)
    return any(k in lab for k in _LABEL_HINTS)


def assign_roles(dimensions: list, details: dict) -> None:
    """Atribuie d.role fiecărei dimensiuni, pe loc."""
    time_code = details.get("matTime")
    caen = {details.get("matCaen1"), details.get("matCaen2")} - {0, None}
    for d in dimensions:
        if is_territorial(d, details):
            d.role = "teritoriu"
        elif time_code and d.dim_code == time_code:
            d.role = "timp"
        elif d.dim_code in caen:
            d.role = "caen"
        elif d.label.strip().lower().startswith("um:"):
            d.role = "um"
        else:
            d.role = "alt"


def is_locality_dimension(dimension, details: dict) -> bool:
    """True dacă dimensiunea ține localități, din details sau din label."""
    return (dimension.dim_code == details.get("nomLoc")
            or "localit" in _norm(dimension.label))


def dimension_levels(dimension, details: dict) -> set:
    """Nivelele acoperite de o singură dimensiune."""
    if not is_territorial(dimension, details):
        return set()
    lab = _norm(dimension.label)
    if dimension.dim_code == details.get("nomLoc") or "localit" in lab:
        return {"localitate"}
    return {option_level(o.label) for o in dimension.options}


def levels_present(dimensions: list, details: dict) -> list[str]:
    """Nivelele teritoriale ale matricei, de la general la specific."""
    found = set()
    for d in dimensions:
        found |= dimension_levels(d, details)
    return [x for x in _LEVEL_ORDER if x in found]


# prefixele de tip din denumirile de localitate, cele lungi primele
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
    """Desface o denumire teritorială în (siruta, nivel, tip, nume).

    Localitățile vin ca 'SIRUTA TIP NUME': '1017 MUNICIPIUL ALBA IULIA',
    '1151 ORAS ABRUD'. Comunele vin fără prefix de tip: '2130 ALBAC'.
    Agregatele și județele nu au SIRUTA: 'TOTAL', 'MACROREGIUNEA UNU',
    'Regiunea NORD-VEST', 'Cluj'.
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
    # comunele nu poarta prefix de tip
    return (siruta, "localitate", "comuna", rest)


def siruta_from_label(label: str) -> int | None:
    """Codul SIRUTA, prefixul numeric al denumirii de localitate.

    '1017 MUNICIPIUL ALBA IULIA' -> 1017. None dacă label-ul nu începe cu cifre
    (ex. 'TOTAL'). Prezent când details.matSiruta e adevărat.
    """
    if not label:
        return None
    head = label.split(maxsplit=1)[0]
    return int(head) if head.isdigit() else None


def group_localities_by_county(locality_dimension) -> dict:
    """Grupează opțiunile de localitate pe județ, prin parent_id.

    parent_id al unei localități e nomItemId-ul județului. Baza chunking-ului
    județ cu județ pentru matricele la nivel de localitate (iterația 3).
    """
    groups = {}
    for opt in locality_dimension.options:
        groups.setdefault(opt.parent_id, []).append(opt)
    return groups
