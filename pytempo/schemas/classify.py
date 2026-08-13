"""Placing an indicator into a family, by the shape of its dimensions.

The family decides how the data is fetched, so it is the criterion get uses to
pick a strategy. A pure function over a registry record, with no network.
"""

FAMILIES = ("judet_localitate", "teritorial_caen", "teritorial_simplu",
            "neteritorial", "alt")


def classify(entry: dict) -> str:
    """An indicator's family, from its registry fields.

    judet_localitate : has a locality dimension. The hard case, downloaded
                       county by county.
    teritorial_caen  : has territory and CAEN, no localities.
    teritorial_simplu: has territory, no CAEN and no localities.
    neteritorial     : no dimension with a territorial role.
    alt              : anything not covered above, for example a record with
                       no dimensions at all. They are listed one by one in the
                       report, because each is a case to read with your eyes.
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
