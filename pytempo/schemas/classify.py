"""Încadrarea unui indicator într-o familie, după forma dimensiunilor lui.

Familia decide cum se aduc datele, deci e criteriul după care get-ul final va
alege strategia. Funcție pură peste o intrare de registry, fără rețea.
"""

FAMILIES = ("judet_localitate", "teritorial_caen", "teritorial_simplu",
            "neteritorial", "alt")


def classify(entry: dict) -> str:
    """Familia unui indicator, din câmpurile lui de registry.

    judet_localitate : are dimensiune de localități. Cazul greu, se descarcă
                       județ cu județ.
    teritorial_caen  : are teritoriu și CAEN, fără localități.
    teritorial_simplu: are teritoriu, fără CAEN și fără localități.
    neteritorial     : nicio dimensiune cu rol teritoriu.
    alt              : ce nu intră în cele de sus, ex. o intrare fără
                       dimensiuni deloc. Lista lor se printează în raport,
                       fiindcă fiecare e un caz de citit cu ochii.
    """
    dims = entry.get("dims") or []
    if not dims:
        return "alt"

    are_teritoriu = any(d.get("role") == "teritoriu" for d in dims)

    if entry.get("has_localities"):
        return "judet_localitate"
    if are_teritoriu and entry.get("has_caen"):
        return "teritorial_caen"
    if are_teritoriu:
        return "teritorial_simplu"
    if not are_teritoriu:
        return "neteritorial"
    return "alt"
