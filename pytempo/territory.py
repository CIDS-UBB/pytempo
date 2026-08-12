"""Rolurile dimensiunilor și nivelele teritoriale, derivate din blocul details.

Principiu de corectitudine: rolul unei dimensiuni vine DETERMINIST din details,
nu din label. details mapează o cheie cunoscută (nomJud, nomLoc, matTime,
matCaen1, matCaen2) la dimCode-ul dimensiunii care joacă acel rol. Labelurile
variază între matrice, dimCode-urile nu. Label-ul se folosește doar ca fallback
pentru unitatea de măsură ('UM: ...').

Atenție: details.matMaxDim e numărul de dimensiuni, nu o limită de celule.
"""

_ROLE_KEYS = (("nomJud", "judet"), ("nomLoc", "localitate"),
              ("matTime", "timp"), ("matCaen1", "caen"), ("matCaen2", "caen"))

# ordinea de la general la specific; doar acestea sunt nivele teritoriale
_LEVEL_ORDER = ("national", "judet", "localitate")


def assign_roles(dimensions: list, details: dict) -> None:
    """Atribuie d.role fiecărei dimensiuni, pe loc.

    details dă dimCode-ul pentru rolurile cunoscute. Cheile absente sau 0
    înseamnă că matricea nu are acel rol.
    """
    role_by_code = {}
    for key, role in _ROLE_KEYS:
        code = details.get(key)
        if code:
            role_by_code[code] = role
    for d in dimensions:
        if d.dim_code in role_by_code:
            d.role = role_by_code[d.dim_code]
        elif d.label.strip().lower().startswith("um:"):
            d.role = "um"
        else:
            d.role = "alt"


def levels_present(dimensions: list) -> list[str]:
    """Nivelele teritoriale ale matricei, de la general la specific.

    O matrice poate avea două dimensiuni teritoriale separate (FOM104D are
    'Judete' și 'Localitati'), caz în care întoarce ['judet', 'localitate'].
    """
    present = {d.role for d in dimensions}
    return [lvl for lvl in _LEVEL_ORDER if lvl in present]


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
