"""Validating the registry against real data, on small slices.

A registry record says what should happen. Validation actually asks for a slice
of a few dozen cells from each indicator and checks the facts: the CSV parses,
the columns line up, the values are numeric, SIRUTA appears where it should,
and a cell picked at random has the same value when requested on its own.

Nothing here is public API. It is used from a development shell:
    from pytempo import schemas
    schemas.validate(sample=15, seed=42)
    schemas.validate()                    # the whole catalogue, with resume
    schemas.spot_check_list(5)
"""
import datetime
import random
import time

from .. import chunking, client, parse, territory
from ..matrix import matrix as fetch_matrix
from . import build
from .build import REGISTRY_VERSION, _save, load_registry

MIN_PER_FAMILY = 3


def _now() -> str:
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")


def stratified_sample(entries: dict, n: int, seed=None) -> list[str]:
    """A random sample, stratified by family, at least MIN_PER_FAMILY each.

    Proportional to family size, but with a floor: the non territorial family
    is 71 percent of the catalogue, and the small families would vanish
    entirely from a strictly proportional sample.
    """
    rnd = random.Random(seed)
    pe_familie = {}
    for cod, e in entries.items():
        if e.get("status") == "ok":
            pe_familie.setdefault(e.get("family", "alt"), []).append(cod)

    total = sum(len(v) for v in pe_familie.values())
    ales = []
    for fam, coduri in sorted(pe_familie.items()):
        cota = max(MIN_PER_FAMILY, round(n * len(coduri) / total)) if total else 0
        cota = min(cota, len(coduri))
        ales += rnd.sample(sorted(coduri), cota)
    rnd.shuffle(ales)
    return ales


def _year_option(dim):
    """The option for the most recent year on a time dimension."""
    cu_an = [(parse._year_of(o.label), o) for o in dim.options]
    cu_an = [(an, o) for an, o in cu_an if an is not None]
    if cu_an:
        return max(cu_an, key=lambda pereche: pereche[0])[1]
    return dim.options[-1]


def _slice_for(m, entry: dict) -> list[list[int]]:
    """The small test slice, per dimension, in API order.

    The target is a single POST of a few dozen cells, whatever the family.
    """
    familie = entry.get("family")
    terr = [d for d in m.dimensions if d.role == "teritoriu"]
    localitati = next((d for d in terr
                       if territory.is_locality_dimension(d, m.details)), None)
    judete = None
    if localitati is not None and len(terr) > 1:
        judete = max((d for d in terr if d is not localitati),
                     key=lambda d: len(d.options))

    # the county we test: the first one that is not the TOTAL aggregate
    judet_ales = None
    if judete is not None:
        judet_ales = next((o for o in judete.options
                           if o.label.strip().upper() != "TOTAL"), None)

    selectie = []
    for d in m.dimensions:
        if d.role == "timp":
            selectie.append([_year_option(d).nom_item_id])
        elif d is localitati and familie == "judet_localitate":
            if judet_ales is not None:
                grupuri = territory.group_localities_by_county(d)
                ids = [o.nom_item_id
                       for o in grupuri.get(judet_ales.nom_item_id, [])]
            else:
                ids = []
            # with no county plus locality pair we take the head of the list
            selectie.append(ids or [o.nom_item_id for o in d.options[:20]])
        elif d is judete and judet_ales is not None:
            selectie.append([judet_ales.nom_item_id])
        elif d.role == "teritoriu":
            selectie.append([o.nom_item_id for o in d.options])
        else:
            selectie.append([d.options[0].nom_item_id])
    return selectie


def _payload(m, selectie) -> dict:
    return {
        "language": "ro",
        "encQuery": chunking.build_encquery(selectie),
        "matCode": m.code,
        "matMaxDim": m.details.get("matMaxDim"),
        "matUMSpec": m.details.get("matUMSpec"),
    }


def _norm_label(text) -> str:
    """Labels in the CSV arrive without the commas of the original name."""
    return " ".join(str(text).replace(",", " ").split()).lower()


def _point_check(m, df) -> str | None:
    """Ask for a single cell of the slice and compare. None when it matches."""
    rand = df.iloc[len(df) // 2]
    selectie = []
    for d in m.dimensions:
        eticheta = _norm_label(rand[d.label.strip()])
        gasit = next((o for o in d.options
                      if _norm_label(o.label) == eticheta), None)
        if gasit is None:
            return (f"cannot map label {rand[d.label.strip()]!r} back to a "
                    f"code on dimension {d.label.strip()!r}")
        selectie.append([gasit.nom_item_id])

    text = client.post_pivot(_payload(m, selectie))
    singur = parse.pivot_csv_to_dataframe(text, m)
    if len(singur) != 1:
        return f"the point cell returned {len(singur)} rows, expected 1"
    a, b = rand["Valoare"], singur.iloc[0]["Valoare"]
    if a != b:
        return f"point cell differs: {a} in the slice, {b} on its own"
    return None


# An indicator that measures a balance can legitimately go negative: a natural
# increase, a migration balance, a change or a difference. Counting those as
# implausible was wrong: POP214A really does record -576 for Arges in 1995.
# The word is looked for in the indicator name and in every dimension label,
# normalized and lowercased.
_BALANCE_WORDS = ("spor", "sold", "migrat", "crestere", "variatia",
                  "diferenta")


def _allows_negative(m) -> bool:
    """Is this a balance style indicator, where negative values are correct?"""
    texte = [m.name] + [d.label for d in m.dimensions]
    return any(cuvant in territory._norm(text)
               for text in texte for cuvant in _BALANCE_WORDS)


def _why_unparsable(m, text: str) -> str:
    """A likely cause for a CSV we could not parse, when we recognize one.

    Both cases seen so far are quirks of what INS sends, not of our request:
    a dimension label containing a newline, which breaks the header across two
    lines, and the confidentiality marker in the value column.
    """
    if any("\n" in (d.label or "") for d in m.dimensions):
        return ("a dimension label contains a newline, so the CSV header "
                "spans two lines")
    randuri = [r for r in text.split("\n") if r.strip()][1:]
    valori = {r.rsplit(",", 1)[-1].strip() for r in randuri if "," in r}
    ne_numerice = {x for x in valori
                   if x and not x.replace(".", "", 1).lstrip("-").isdigit()}
    if ne_numerice:
        return (f"the value column carries non numeric markers "
                f"{sorted(ne_numerice)[:3]}, most likely INS flags for "
                f"suppressed or unavailable data")
    return "unrecognized response shape"


def _checks(m, entry, df) -> str | None:
    """The checks on the slice that came back. None when all is well."""
    if entry.get("has_siruta"):
        tidy = parse.standardize(df, m)
        loc = [d for d in m.dimensions
               if d.role == "teritoriu"
               and territory.is_locality_dimension(d, m.details)]
        for d in loc:
            coloana = tidy[f"{d.label.strip()}_siruta"]
            localitati = tidy[f"{d.label.strip()}_nivel"] == "localitate"
            if localitati.any() and coloana[localitati].isna().all():
                return (f"has_siruta is True, but SIRUTA is empty for every "
                        f"locality in {d.label.strip()!r}")

    um = [d for d in m.dimensions if d.role == "um"]
    if any("persoane" in territory._norm(d.label) for d in um) \
            and not _allows_negative(m):
        negative = (df["Valoare"] < 0).sum()
        if negative:
            return f"{negative} negative values where the unit counts people"

    return _point_check(m, df)


def validate(sample: int | None = None, codes: list[str] | None = None,
             resume: bool = True, progress: bool = True, delay: float = 1.0,
             seed=None, path=None) -> dict:
    """Ask for a small slice of each indicator and check what came back.

    codes=[...] validates exactly that list, which is the targeted mode used to
    recheck a handful after a fix. sample=N takes a sample stratified by
    family; both omitted takes the whole catalogue, for the long run. resume
    skips whatever already passed at the same registry version, so the long run
    can be stopped and restarted.

    A slice that fails to parse is recorded as needs_review rather than error:
    those are quirks of what INS sent, not faults of the extraction, and each
    one is a documented exception to read by hand.
    """
    path = path or build.REGISTRY_PATH
    date = load_registry(path)
    if not date:
        print("There is no registry.json. Run schemas.build_registry().")
        return {}
    entries = date["entries"]

    if codes:
        lipsa = [c for c in codes if c not in entries]
        if lipsa:
            raise ValueError(f"codes not in the registry: {lipsa}")
        coduri = list(codes)
    elif sample:
        coduri = stratified_sample(entries, sample, seed=seed)
    else:
        coduri = [c for c, e in entries.items() if e.get("status") == "ok"]
    if resume:
        coduri = [c for c in coduri
                  if not (entries[c].get("validation") == "ok"
                          and entries[c].get("validated_version")
                          == REGISTRY_VERSION)]

    total = len(coduri)
    pornit = time.time()
    for i, cod in enumerate(coduri, 1):
        e = entries[cod]
        try:
            m = fetch_matrix(cod)
            selectie = _slice_for(m, e)
            celule = chunking.cells(selectie)
            text = client.post_pivot(_payload(m, selectie))
            e["slice_cells"] = celule
            try:
                df = parse.pivot_csv_to_dataframe(text, m)
            except ValueError as exc:
                # the CSV itself is off, so this is about what INS sent, not
                # about our extraction; it goes to a human, not to the fail pile
                e["validation"] = (f"needs_review: {_why_unparsable(m, text)}"
                                   f" ({exc})")
            else:
                if df.empty:
                    e["validation"] = "empty"
                else:
                    motiv = _checks(m, e, df)
                    e["validation"] = f"error: {motiv}" if motiv else "ok"
        except Exception as exc:
            e["validation"] = f"error: {type(exc).__name__}: {exc}"
            e["slice_cells"] = 0
        e["validated_at"] = _now()
        e["validated_version"] = REGISTRY_VERSION

        if progress:
            scurs = time.time() - pornit
            ramas = scurs / i * (total - i)
            print(f"\rvalidating: {i}/{total}, ~{ramas / 60:.1f} min left",
                  end="", flush=True)
        if delay and i < total:
            time.sleep(delay)
    if progress and total:
        print()

    _save(date, path)
    if progress:
        validation_report(date)
    return date


def validation_report(date: dict | None = None, path=None) -> None:
    """The validation report: how many ok, how many empty, what went wrong."""
    date = date or load_registry(path)
    if not date:
        print("There is no registry.json.")
        return
    entries = date["entries"]
    validate_le = {c: e for c, e in entries.items() if e.get("validation")}

    ok = [c for c, e in validate_le.items() if e["validation"] == "ok"]
    goi = [c for c, e in validate_le.items() if e["validation"] == "empty"]
    erori = {c: e["validation"] for c, e in validate_le.items()
             if e["validation"].startswith("error:")}
    de_citit = {c: e["validation"] for c, e in validate_le.items()
                if e["validation"].startswith("needs_review:")}

    print(f"\nValidation: {len(validate_le)} indicators checked")
    print(f"  ok           : {len(ok)}")
    print(f"  empty        : {len(goi)}" + (f"  {goi[:8]}" if goi else ""))
    print(f"  errors       : {len(erori)}")
    for cod, motiv in erori.items():
        print(f"    {cod:10} {motiv[:110]}")
    print(f"  needs review : {len(de_citit)}"
          + ("  (documented exceptions, not failures)" if de_citit else ""))
    for cod, motiv in de_citit.items():
        print(f"    {cod:10} {motiv[:110]}")

    fara_siruta = [c for c, e in entries.items()
                   if e.get("has_localities") and not e.get("has_siruta")]
    if fara_siruta:
        print("\nlocalities without SIRUTA (tidy leaves the _siruta column "
              "empty):")
        for cod in fara_siruta:
            e = entries[cod]
            print(f"  {cod:10} {e.get('name', '')[:70]}")
            print(f"             validation: {e.get('validation', 'not checked')}")


def spot_check_list(n: int = 10, seed=None, path=None) -> list[dict]:
    """A list of cells to check BY EYE on the INS site.

    Why manual: the TEMPO site and the API are the same system, so an automatic
    comparison would compare the API with itself and always agree. The only
    independent check is a person reading the site, and our job is to hand them
    a ready made list.
    """
    date = load_registry(path)
    if not date:
        print("There is no registry.json.")
        return []
    ok = sorted(c for c, e in date["entries"].items()
                if e.get("validation") == "ok")
    if not ok:
        print("No indicator validated ok. Run schemas.validate(...).")
        return []

    rnd = random.Random(seed)
    randuri = []
    for cod in rnd.sample(ok, min(n, len(ok))):
        e = date["entries"][cod]
        try:
            m = fetch_matrix(cod)
            df = parse.pivot_csv_to_dataframe(
                client.post_pivot(_payload(m, _slice_for(m, e))), m)
            if df.empty:
                continue
            rand = df.iloc[len(df) // 2]
            combinatie = {d.label.strip(): rand[d.label.strip()]
                          for d in m.dimensions}
            randuri.append({"code": cod, "name": e.get("name", ""),
                            "combination": combinatie,
                            "value": rand["Valoare"], "url": e.get("endpoint")})
        except Exception as exc:
            print(f"  {cod}: cannot compose a cell ({exc})")

    print(f"\nTo check by hand on the site, {len(randuri)} cells:")
    for r in randuri:
        print(f"\n{r['code']}  {r['name'][:70]}")
        for eticheta, valoare in r["combination"].items():
            print(f"    {eticheta[:40]:42} {valoare}")
        print(f"    {'OUR VALUE':42} {r['value']}")
        print(f"    {r['url']}")
    return randuri
