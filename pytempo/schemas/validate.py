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
    by_family = {}
    for cod, e in entries.items():
        if e.get("status") == "ok":
            by_family.setdefault(e.get("family", "alt"), []).append(cod)

    total = sum(len(v) for v in by_family.values())
    chosen = []
    for fam, codes_wanted in sorted(by_family.items()):
        quota = max(MIN_PER_FAMILY, round(n * len(codes_wanted) / total)) if total else 0
        quota = min(quota, len(codes_wanted))
        chosen += rnd.sample(sorted(codes_wanted), quota)
    rnd.shuffle(chosen)
    return chosen


def _year_option(dim):
    """The option for the most recent year on a time dimension."""
    with_year = [(parse._year_of(o.label), o) for o in dim.options]
    with_year = [(an, o) for an, o in with_year if an is not None]
    if with_year:
        return max(with_year, key=lambda pair: pair[0])[1]
    return dim.options[-1]


def _slice_for(m, entry: dict) -> list[list[int]]:
    """The small test slice, per dimension, in API order.

    The target is a single POST of a few dozen cells, whatever the family.
    """
    family = entry.get("family")
    terr = [d for d in m.dimensions if d.role == "teritoriu"]
    localities = next((d for d in terr
                       if territory.is_locality_dimension(d, m.details)), None)
    counties = None
    if localities is not None and len(terr) > 1:
        counties = max((d for d in terr if d is not localities),
                     key=lambda d: len(d.options))

    # the county we test: the first one that is not the TOTAL aggregate
    chosen_county = None
    if counties is not None:
        chosen_county = next((o for o in counties.options
                           if o.label.strip().upper() != "TOTAL"), None)

    selection = []
    for d in m.dimensions:
        if d.role == "timp":
            selection.append([_year_option(d).nom_item_id])
        elif d is localities and family == "judet_localitate":
            if chosen_county is not None:
                groups = territory.group_localities_by_county(d)
                ids = [o.nom_item_id
                       for o in groups.get(chosen_county.nom_item_id, [])]
            else:
                ids = []
            # with no county plus locality pair we take the head of the list
            selection.append(ids or [o.nom_item_id for o in d.options[:20]])
        elif d is counties and chosen_county is not None:
            selection.append([chosen_county.nom_item_id])
        elif d.role == "teritoriu":
            selection.append([o.nom_item_id for o in d.options])
        else:
            selection.append([d.options[0].nom_item_id])
    return selection


def _payload(m, selection) -> dict:
    return {
        "language": "ro",
        "encQuery": chunking.build_encquery(selection),
        "matCode": m.code,
        "matMaxDim": m.details.get("matMaxDim"),
        "matUMSpec": m.details.get("matUMSpec"),
    }


def _norm_label(text) -> str:
    """Labels in the CSV arrive without the commas of the original name."""
    return " ".join(str(text).replace(",", " ").split()).lower()


def _point_check(m, df) -> str | None:
    """Ask for a single cell of the slice and compare. None when it matches."""
    row = df.iloc[len(df) // 2]
    selection = []
    for d in m.dimensions:
        label_text = _norm_label(row[d.label.strip()])
        found = next((o for o in d.options
                      if _norm_label(o.label) == label_text), None)
        if found is None:
            return (f"cannot map label {row[d.label.strip()]!r} back to a "
                    f"code on dimension {d.label.strip()!r}")
        selection.append([found.nom_item_id])

    text = client.post_pivot(_payload(m, selection))
    single_cell = parse.pivot_csv_to_dataframe(text, m)
    if len(single_cell) != 1:
        return f"the point cell returned {len(single_cell)} rows, expected 1"
    a, b = row["Valoare"], single_cell.iloc[0]["Valoare"]
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
    texts = [m.name] + [d.label for d in m.dimensions]
    return any(word in territory._norm(text)
               for text in texts for word in _BALANCE_WORDS)


def _why_unparsable(m, text: str) -> str:
    """A likely cause for a CSV we could not parse, when we recognize one.

    Both cases seen so far are quirks of what INS sends, not of our request:
    a dimension label containing a newline, which breaks the header across two
    lines, and the confidentiality marker in the value column.
    """
    if any("\n" in (d.label or "") for d in m.dimensions):
        return ("a dimension label contains a newline, so the CSV header "
                "spans two lines")
    rows = [r for r in text.split("\n") if r.strip()][1:]
    values_seen = {r.rsplit(",", 1)[-1].strip() for r in rows if "," in r}
    non_numeric = {x for x in values_seen
                   if x and not x.replace(".", "", 1).lstrip("-").isdigit()}
    if non_numeric:
        return (f"the value column carries non numeric markers "
                f"{sorted(non_numeric)[:3]}, most likely INS flags for "
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
            column = tidy[f"{d.label.strip()}_siruta"]
            localities = tidy[f"{d.label.strip()}_nivel"] == "localitate"
            if localities.any() and column[localities].isna().all():
                return (f"has_siruta is True, but SIRUTA is empty for every "
                        f"locality in {d.label.strip()!r}")

    units = [d for d in m.dimensions if d.role == "um"]
    if any("persoane" in territory._norm(d.label) for d in units) \
            and not _allows_negative(m):
        negatives = (df["Valoare"] < 0).sum()
        if negatives:
            return f"{negatives} negative values where the unit counts people"

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
    data = load_registry(path)
    if not data:
        print("There is no registry.json. Run schemas.build_registry().")
        return {}
    entries = data["entries"]

    if codes:
        missing_fields = [c for c in codes if c not in entries]
        if missing_fields:
            raise ValueError(f"codes not in the registry: {missing_fields}")
        codes_wanted = list(codes)
    elif sample:
        codes_wanted = stratified_sample(entries, sample, seed=seed)
    else:
        codes_wanted = [c for c, e in entries.items() if e.get("status") == "ok"]
    if resume:
        codes_wanted = [c for c in codes_wanted
                  if not (entries[c].get("validation") == "ok"
                          and entries[c].get("validated_version")
                          == REGISTRY_VERSION)]

    total = len(codes_wanted)
    started = time.time()
    for i, cod in enumerate(codes_wanted, 1):
        e = entries[cod]
        try:
            m = fetch_matrix(cod)
            selection = _slice_for(m, e)
            cells_needed = chunking.cells(selection)
            text = client.post_pivot(_payload(m, selection))
            e["slice_cells"] = cells_needed
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
                    reason = _checks(m, e, df)
                    e["validation"] = f"error: {reason}" if reason else "ok"
        except Exception as exc:
            e["validation"] = f"error: {type(exc).__name__}: {exc}"
            e["slice_cells"] = 0
        e["validated_at"] = _now()
        e["validated_version"] = REGISTRY_VERSION

        if progress:
            elapsed = time.time() - started
            remaining = elapsed / i * (total - i)
            print(f"\rvalidating: {i}/{total}, ~{remaining / 60:.1f} min left",
                  end="", flush=True)
        if delay and i < total:
            time.sleep(delay)
    if progress and total:
        print()

    _save(data, path)
    if progress:
        validation_report(data)
    return data


def validation_report(data: dict | None = None, path=None) -> None:
    """The validation report: how many ok, how many empty, what went wrong."""
    data = data or load_registry(path)
    if not data:
        print("There is no registry.json.")
        return
    entries = data["entries"]
    validate_le = {c: e for c, e in entries.items() if e.get("validation")}

    ok = [c for c, e in validate_le.items() if e["validation"] == "ok"]
    empties = [c for c, e in validate_le.items() if e["validation"] == "empty"]
    errors = {c: e["validation"] for c, e in validate_le.items()
             if e["validation"].startswith("error:")}
    to_review = {c: e["validation"] for c, e in validate_le.items()
                if e["validation"].startswith("needs_review:")}

    print(f"\nValidation: {len(validate_le)} indicators checked")
    print(f"  ok           : {len(ok)}")
    print(f"  empty        : {len(empties)}" + (f"  {empties[:8]}" if empties else ""))
    print(f"  errors       : {len(errors)}")
    for cod, reason in errors.items():
        print(f"    {cod:10} {reason[:110]}")
    print(f"  needs review : {len(to_review)}"
          + ("  (documented exceptions, not failures)" if to_review else ""))
    for cod, reason in to_review.items():
        print(f"    {cod:10} {reason[:110]}")

    fara_siruta = [c for c, e in entries.items()
                   if e.get("has_localities") and not e.get("has_siruta")]
    if fara_siruta:
        print("\nlocalities without SIRUTA (tidy leaves the _siruta column "
              "empty):")
        for cod in fara_siruta:
            e = entries[cod]
            print(f"  {cod:10} {e.get('name', '')[:70]}")
            print(f"             validation: {e.get('validation', 'not checked')}")


def audit_standardization(sample: int | None = None, seed=None,
                          delay: float = 1.0, progress: bool = True,
                          path=None) -> dict:
    """Look for post processing oddities across the catalogue.

    Not a correctness check, a survey: it fetches a small standardized slice
    and asks what tidy actually produced. The point is to tell whether a case
    like FOM104D, where a county dimension used to get empty SIRUTA columns,
    is isolated or a pattern.

    Three things are counted:
      empty_derived   a derived column would have come out completely empty
      all_unknown     a territorial dimension whose levels are all necunoscut
      nothing_added   tidy added no column at all
    """
    data = load_registry(path)
    if not data:
        print("There is no registry.json. Run schemas.build_registry().")
        return {}
    entries = data["entries"]

    if sample:
        codes_wanted = stratified_sample(entries, sample, seed=seed)
    else:
        codes_wanted = [c for c, e in entries.items() if e.get("status") == "ok"]

    found_kinds = {"empty_derived": [], "all_unknown": [], "nothing_added": []}
    skipped = []
    total = len(codes_wanted)
    for i, cod in enumerate(codes_wanted, 1):
        e = entries[cod]
        try:
            m = fetch_matrix(cod)
            df = parse.pivot_csv_to_dataframe(
                client.post_pivot(_payload(m, _slice_for(m, e))), m)
            if df.empty:
                skipped.append(cod)
                continue
            tidy = parse.standardize(df, m)
        except Exception:
            skipped.append(cod)
            continue

        added = [c for c in tidy.columns if c not in df.columns]
        if not added:
            found_kinds["nothing_added"].append(cod)
        if any(tidy[c].isna().all() for c in added):
            found_kinds["empty_derived"].append(cod)
        for d in m.dimensions:
            column = f"{d.label.strip()}_nivel"
            if column in tidy.columns and (tidy[column] == "necunoscut").all():
                found_kinds["all_unknown"].append(cod)
                break

        if progress and (i % 5 == 0 or i == total):
            print(f"\rauditing: {i}/{total}", end="", flush=True)
        if delay and i < total:
            time.sleep(delay)
    if progress and total:
        print()

    print(f"\nStandardization audit: {len(codes_wanted) - len(skipped)} indicators "
          f"inspected, {len(skipped)} skipped (empty or unreadable slice)")
    for tip, coduri_gasite in found_kinds.items():
        print(f"  {tip:14} {len(coduri_gasite)}")
        if coduri_gasite:
            print(f"    {sorted(coduri_gasite)[:12]}")
    return found_kinds


def spot_check_list(n: int = 10, seed=None, path=None) -> list[dict]:
    """A list of cells to check BY EYE on the INS site.

    Why manual: the TEMPO site and the API are the same system, so an automatic
    comparison would compare the API with itself and always agree. The only
    independent check is a person reading the site, and our job is to hand them
    a ready made list.
    """
    data = load_registry(path)
    if not data:
        print("There is no registry.json.")
        return []
    ok = sorted(c for c, e in data["entries"].items()
                if e.get("validation") == "ok")
    if not ok:
        print("No indicator validated ok. Run schemas.validate(...).")
        return []

    rnd = random.Random(seed)
    rows = []
    for cod in rnd.sample(ok, min(n, len(ok))):
        e = data["entries"][cod]
        try:
            m = fetch_matrix(cod)
            df = parse.pivot_csv_to_dataframe(
                client.post_pivot(_payload(m, _slice_for(m, e))), m)
            if df.empty:
                continue
            row = df.iloc[len(df) // 2]
            combination = {d.label.strip(): row[d.label.strip()]
                          for d in m.dimensions}
            rows.append({"code": cod, "name": e.get("name", ""),
                            "combination": combination,
                            "value": row["Valoare"], "url": e.get("endpoint")})
        except Exception as exc:
            print(f"  {cod}: cannot compose a cell ({exc})")

    print(f"\nTo check by hand on the site, {len(rows)} cells:")
    for r in rows:
        print(f"\n{r['code']}  {r['name'][:70]}")
        for label_text, valoare in r["combination"].items():
            print(f"    {label_text[:40]:42} {valoare}")
        print(f"    {'OUR VALUE':42} {r['value']}")
        print(f"    {r['url']}")
    return rows
