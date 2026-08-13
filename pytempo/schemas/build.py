"""Building the schema registry: the internal census of the catalogue.

registry.json lives inside the package and is versioned in the repo, so anyone
who clones already has the map without waiting minutes for a build. Fetching
the metadata is also the endpoint test: status ok means the endpoint answered.

Nothing here is public API. It is used from a development shell:
    from pytempo import schemas
    schemas.build_registry()
    schemas.report()
"""
import datetime
import json
import pathlib

from .. import client, endpoints, territory
from ..chunking import MAX_CELLS
from .classify import FAMILIES, classify

REGISTRY_VERSION = 1
REGISTRY_PATH = pathlib.Path(__file__).with_name("registry.json")

# 0.40s per call, measured against INS; that is where the estimate comes from
SECUNDE_PER_APEL = 0.4


def load_registry(path: pathlib.Path | None = None) -> dict | None:
    """The registry from disk, or None if it does not exist.

    Raises ValueError on an unknown schema version, so a missed migration gives
    a clear message instead of a KeyError somewhere further down.
    """
    path = path or REGISTRY_PATH
    if not path.exists():
        return None
    date = json.loads(path.read_text(encoding="utf-8"))
    versiune = date.get("registry_version")
    if versiune != REGISTRY_VERSION:
        raise ValueError(
            f"registry.json has registry_version={versiune!r}, but the code "
            f"expects {REGISTRY_VERSION}. Run "
            f"schemas.build_registry(refresh=True) to rebuild it.")
    return date


def _save(date: dict, path: pathlib.Path) -> None:
    """Write the registry canonically: sorted keys, one field per line.

    The file is versioned in the repo, so its shape matters: sorting keeps it
    stable between rebuilds, and indentation keeps the diff readable, so a
    change on the INS side shows up line by line.
    """
    path.write_text(
        json.dumps(date, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")


def _entry_from_matrix(m) -> dict:
    """One indicator's registry record, from its metadata."""
    dims = [{"label": d.label.strip(), "role": d.role,
             "n_options": len(d.options), "dim_code": d.dim_code}
            for d in m.dimensions]
    celule = 1
    for d in m.dimensions:
        celule *= len(d.options)

    entry = {
        "name": m.name,
        "endpoint": endpoints.matrix(m.code),
        "dims": dims,
        "levels": m.levels,
        "has_localities": any(
            d.role == "teritoriu"
            and territory.is_locality_dimension(d, m.details)
            for d in m.dimensions),
        "has_caen": any(d.role == "caen" for d in m.dimensions),
        "has_sex": any("sex" in territory._norm(d.label) for d in m.dimensions),
        "has_siruta": m.has_siruta,
        "total_cells": celule if m.dimensions else 0,
        "periodicity": list(m.periodicity or []),
        "domain": m.ancestors[0]["name"] if m.ancestors else "",
        "last_updated": m.last_updated,
        "fetched_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        "status": "ok",
    }
    # clean the embedded HTML out of the domain name, as everywhere else
    from ..matrix import _clean
    entry["domain"] = _clean(entry["domain"])
    entry["family"] = classify(entry)
    entry["fetch_plan"] = plan_for(entry)
    return entry


def _county_dim(entry: dict) -> dict | None:
    """The county dimension of an indicator with localities, if it has one.

    Not all do: TMP1173 has a single territorial dimension, monitoring
    stations, so it cannot be split by county.
    """
    terr = [d for d in (entry.get("dims") or []) if d.get("role") == "teritoriu"]
    if len(terr) < 2:
        return None
    localitati = max(terr, key=lambda d: d.get("n_options") or 0)
    restul = [d for d in terr if d is not localitati]
    return restul[0] if restul else None


def plan_for(entry: dict) -> dict:
    """An indicator's fetch plan, computed from its registry record.

    get is a plain executor of this plan: it reads the strategy, runs it and
    applies tidy. No decisions at runtime, no cost arithmetic at request time.

    strategy: 'single' under the threshold; 'by_county' for matrices with
    localities that also have a county dimension; 'split:<label>' otherwise,
    on the dimension with the most options.
    """
    dims = entry.get("dims") or []
    levels = entry.get("levels") or []
    celule = entry.get("total_cells") or 0

    # 'necunoscut' is not a level to ask for: names that do not fit the
    # nomenclator do not form a useful slice. The finest REAL level is what
    # counts, and if there is none, get() applies no territorial filter.
    fin = [lv for lv in territory._LEVEL_ORDER
           if lv in levels and lv != "necunoscut"]
    plan = {
        "default_level": fin[-1] if fin else None,
        "tidy_ready": any(d.get("role") in ("teritoriu", "timp") for d in dims),
    }

    if not dims or celule <= MAX_CELLS:
        plan["strategy"] = "single"
        plan["est_requests"] = 1
        return plan

    judete = (_county_dim(entry)
              if entry.get("family") == "judet_localitate" else None)
    if judete:
        plan["strategy"] = "by_county"
        plan["est_requests"] = judete.get("n_options") or 1
        return plan

    # over the threshold with no county plus locality pair: split on the
    # largest dimension, so each request fits under the threshold
    cea_mai_mare = max(dims, key=lambda d: d.get("n_options") or 0)
    n = cea_mai_mare.get("n_options") or 1
    pe_optiune = max(1, celule // n)
    pe_cerere = max(1, MAX_CELLS // pe_optiune)
    plan["strategy"] = f"split:{cea_mai_mare.get('label', '')}"
    plan["est_requests"] = -(-n // pe_cerere)
    return plan


def refresh_plans(path: pathlib.Path | None = None, progress: bool = True) -> dict:
    """Recompute fetch_plan for the whole registry, with no network."""
    path = path or REGISTRY_PATH
    date = load_registry(path)
    if not date:
        print("There is no registry.json. Run schemas.build_registry().")
        return {}
    for e in date["entries"].values():
        if e.get("status") == "ok":
            e["fetch_plan"] = plan_for(e)
    _save(date, path)
    if progress:
        from collections import Counter
        strategii = Counter(
            (e.get("fetch_plan") or {}).get("strategy", "").split(":")[0]
            for e in date["entries"].values() if e.get("status") == "ok")
        print(f"plans recomputed: {dict(strategii)}")
    return date


_VALIDATION_FIELDS = ("validation", "validated_at", "validated_version",
                      "slice_cells")


def _keep_validation(veche: dict | None, noua: dict) -> dict:
    """Carry validation forward across a rebuild of the record.

    A rebuild recomputes the shape of the indicator, but it does not
    invalidate a check made against real data, as long as INS has not updated
    it meanwhile. If last_updated changed, the old validation is dropped and
    resume will redo it.
    """
    if not veche or veche.get("last_updated") != noua.get("last_updated"):
        return noua
    for camp in _VALIDATION_FIELDS:
        if camp in veche:
            noua[camp] = veche[camp]
    return noua


def _uncached(coduri) -> list[str]:
    """The codes whose metadata is NOT in the disk cache."""
    return [c for c in coduri
            if not client._cache_path(endpoints.matrix(c)).exists()]


def _ask(nr_apeluri: int) -> bool:
    minute = max(1, round(nr_apeluri * SECUNDE_PER_APEL / 60))
    print(f"The build needs {nr_apeluri} uncached metadata records,")
    print(f"about {minute} minutes of network. The rest come from cache.")
    try:
        raspuns = input("Build the registry now? [y/N] ")
    except (EOFError, OSError):
        return False
    return raspuns.strip().lower() in ("y", "yes", "d", "da")


def build_registry(progress: bool = True, refresh: bool = False,
                   incremental: bool = True, confirm: bool = True,
                   path: pathlib.Path | None = None) -> dict:
    """The catalogue census: one registry record per indicator.

    incremental=True keeps existing records with status ok and only fetches new
    codes. Note: that way changes INS made to an already registered indicator
    are NOT seen, because its metadata is not re-read. That is what
    refresh=True is for, which redoes everything, bypassing the metadata cache.
    """
    from .. import catalog
    from ..matrix import matrix as fetch_matrix

    path = path or REGISTRY_PATH
    vechi = {}
    if not refresh:
        existent = load_registry(path)
        if existent:
            vechi = existent.get("entries", {})

    randuri = catalog.load_index()
    de_facut = [r["code"] for r in randuri]
    if incremental and not refresh:
        de_facut = [c for c in de_facut
                    if vechi.get(c, {}).get("status") != "ok"]

    if confirm and de_facut:
        lipsesc = de_facut if refresh else _uncached(de_facut)
        if lipsesc and not _ask(len(lipsesc)):
            print("Fine, not building. The registry stays as it was.")
            return {"registry_version": REGISTRY_VERSION, "entries": vechi}

    entries = dict(vechi)
    total = len(de_facut)
    for i, cod in enumerate(de_facut, 1):
        try:
            noua = _entry_from_matrix(fetch_matrix(cod, refresh=refresh))
            entries[cod] = _keep_validation(vechi.get(cod), noua)
        except Exception as e:
            entries[cod] = {"name": "", "status": f"error: {e}",
                            "family": "alt", "dims": [], "levels": [],
                            "total_cells": 0}
        if progress and (i % 10 == 0 or i == total):
            print(f"\rbuilding the registry: {i}/{total}", end="", flush=True)
    if progress and total:
        print()

    date = {"registry_version": REGISTRY_VERSION, "entries": entries}
    _save(date, path)
    if progress:
        print(f"registry saved to {path}, {len(entries)} indicators")
        report(date)
    return date


def report(date: dict | None = None, path: pathlib.Path | None = None) -> None:
    """Reprint the census from the registry, without rebuilding."""
    date = date or load_registry(path)
    if not date:
        print("There is no registry.json. Run schemas.build_registry().")
        return

    entries = date.get("entries", {})
    total = len(entries)
    print(f"\nRegistry, version {date.get('registry_version')}: "
          f"{total} indicators")

    print("\nfamilies")
    for fam in FAMILIES:
        n = sum(1 for e in entries.values() if e.get("family") == fam)
        if n:
            print(f"  {fam:20} {n:5}  {100.0 * n / total:5.1f}%")

    print("\ndomains")
    domenii = {}
    for e in entries.values():
        domenii[e.get("domain") or "(no domain)"] = domenii.get(
            e.get("domain") or "(no domain)", 0) + 1
    for nume, n in sorted(domenii.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  {nume[:70]}")

    cu_siruta = sum(1 for e in entries.values() if e.get("has_siruta"))
    mari = [c for c, e in entries.items()
            if (e.get("total_cells") or 0) > MAX_CELLS]
    print(f"\nwith SIRUTA        : {cu_siruta}")
    print(f"over {MAX_CELLS} cells : {len(mari)} (these need splitting)")

    erori = {c: e["status"] for c, e in entries.items()
             if e.get("status") != "ok"}
    altele = [c for c, e in entries.items()
              if e.get("family") == "alt" and c not in erori]
    print(f"\nfamily 'alt'       : {len(altele)}")
    for c in altele:
        e = entries[c]
        print(f"  {c:10} {len(e.get('dims') or [])} dimensions, "
              f"{e.get('name', '')[:60]}")
    print(f"errors             : {len(erori)}")
    for c, motiv in erori.items():
        print(f"  {c:10} {motiv[:90]}")


def registry_as_index(path: pathlib.Path | None = None) -> dict | None:
    """The registry, in the shape the search filters read.

    A gentle migration: search prefers the registry, but carries on with the
    older data/levels_index.json if the registry is missing.
    """
    date = load_registry(path)
    if not date:
        return None
    return {
        cod: {"levels": e.get("levels") or [],
              "periodicity": e.get("periodicity") or [],
              "has_caen": bool(e.get("has_caen")),
              "domain": e.get("domain") or ""}
        for cod, e in date.get("entries", {}).items()
        if e.get("status") == "ok"
    }
