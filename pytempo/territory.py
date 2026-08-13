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
import difflib
import re
from typing import Literal

_TERRITORY_KEYS = ("nomJud", "nomLoc", "matRegJ")

# de la general la specific; 'necunoscut' sta la coada, pentru denumirile
# teritoriale care nu se incadreaza in nomenclatorul administrativ
_LEVEL_ORDER = ("national", "macroregiune", "regiune", "judet", "localitate",
                "necunoscut")

# acelasi lucru, ca tip: editoarele sugereaza valorile la tastare.
# Un test tine Literal-ul si tuplul sincronizate.
Level = Literal["national", "macroregiune", "regiune", "judet", "localitate",
                "necunoscut"]

# cele 42 de judete plus variantele de Bucuresti din datele INS, normalizate.
# Fara lista asta, orice denumire teritoriala nerecunoscuta cadea pe 'judet',
# iar statiile de monitorizare ale unui indicator de mediu ieseau judete.
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

# totalul national nu se scrie mereu 'TOTAL'; unele matrice AMIGO si CON il
# numesc 'Nivel National'
_NATIONAL_LABELS = frozenset(("nivel national", "total national"))

# cate optiuni ne uitam ca sa decidem daca o dimensiune chiar tine localitati
_SIRUTA_SAMPLE = 20


def level_error(nume, disponibile, cod: str | None = None) -> ValueError:
    """Eroarea pentru un nivel invalid: ce e posibil, plus ce ai vrut probabil.

    Același format în search și în get; diferă doar lista de valori posibile,
    fiindcă la un indicator anume conteaza nivelele lui, nu toate.
    """
    disponibile = list(disponibile)
    unde = f" la {cod}" if cod else ""
    mesaj = (f"nivel necunoscut {nume!r}{unde}. "
             f"Posibile: {', '.join(disponibile) or 'niciunul'}.")
    apropiat = difflib.get_close_matches(str(nume).lower(), disponibile, n=1)
    if apropiat:
        mesaj += f" Poate ai vrut {apropiat[0]!r}?"
    return ValueError(mesaj)

# cuvinte care tradeaza o dimensiune teritoriala cand details tace
_LABEL_HINTS = ("judet", "localit", "macroregiun", "regiun")


def _norm(s: str) -> str:
    """Minuscule, fără diacritice, ca 'județe' să prindă 'judete'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return (s or "").lower().translate(repl)


def option_level(label: str) -> str:
    """Nivelul unei opțiuni teritoriale, după denumire.

    Agregatele se recunosc după prefix. Județul se recunoaște prin apartenența
    la nomenclatorul real, nu ca implicit: altfel orice denumire teritorială
    necunoscută, de la stații de monitorizare la puncte de trecere a
    frontierei, ar fi ieșit județ.
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
    """dimCode-urile marcate teritorial în details. Valorile 0 nu contează."""
    return {details[k] for k in _TERRITORY_KEYS if details.get(k)}


def is_territorial(dimension, details: dict) -> bool:
    """True dacă dimensiunea e teritorială, din details sau din label."""
    if dimension.dim_code in _territory_dimcodes(details):
        return True
    lab = _norm(dimension.label)
    return any(k in lab for k in _LABEL_HINTS)


def is_caen(dimension, details: dict) -> bool:
    """True dacă dimensiunea e o clasificare CAEN, din details sau din label.

    Simetric cu is_territorial: INS nu semnalează mereu CAEN-ul în details.
    FOM104F are matCaen1 și matCaen2 pe 0, deși are o dimensiune
    'CAEN Rev.2 (activitati ale economiei nationale)'.
    """
    coduri = {details.get("matCaen1"), details.get("matCaen2")} - {0, None}
    if dimension.dim_code in coduri:
        return True
    return "caen" in _norm(dimension.label)


def assign_roles(dimensions: list, details: dict) -> None:
    """Atribuie d.role fiecărei dimensiuni, pe loc.

    Ordinea contează: teritoriu, timp, caen, um, apoi alt.
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
    """Opțiunile poartă majoritar prefix numeric SIRUTA?

    Ne uităm doar pe un eșantion: e o confirmare, nu un recensământ.
    """
    optiuni = [o for o in dimension.options
               if (o.label or "").strip().upper() != "TOTAL"][:_SIRUTA_SAMPLE]
    if not optiuni:
        return False
    cu_cod = sum(1 for o in optiuni if siruta_from_label(o.label) is not None)
    return cu_cod * 2 > len(optiuni)


def is_locality_dimension(dimension, details: dict) -> bool:
    """True dacă dimensiunea chiar ține localități.

    details.nomLoc e semnalul autoritar al INS și se ia ca atare. Label-ul
    singur nu ajunge: TMP1173 are o dimensiune numită 'Statii de monitorizare
    de tip fond urban - Localitate' care ține stații, nu localități. De aceea
    label-ul cere confirmare, fie din matSiruta, fie din prefixele numerice
    ale opțiunilor.
    """
    if dimension.dim_code == details.get("nomLoc"):
        return True
    if "localit" not in _norm(dimension.label):
        return False
    return bool(details.get("matSiruta")) or _looks_like_siruta(dimension)


def dimension_levels(dimension, details: dict) -> set:
    """Nivelele acoperite de o singură dimensiune.

    O dimensiune de localități confirmată dă direct 'localitate'. Una care
    doar se numește așa, fără confirmare, își spune nivelele din opțiuni, ceea
    ce pentru stații de monitorizare înseamnă 'necunoscut'.
    """
    if not is_territorial(dimension, details):
        return set()
    if is_locality_dimension(dimension, details):
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
