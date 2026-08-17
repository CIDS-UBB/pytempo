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
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("registry_version")
    if version != REGISTRY_VERSION:
        raise ValueError(
            f"registry.json has registry_version={version!r}, but the code "
            f"expects {REGISTRY_VERSION}. Run "
            f"schemas.build_registry(refresh=True) to rebuild it.")
    return data


def _save(data: dict, path: pathlib.Path) -> None:
    """Write the registry canonically: sorted keys, one field per line.

    The file is versioned in the repo, so its shape matters: sorting keeps it
    stable between rebuilds, and indentation keeps the diff readable, so a
    change on the INS side shows up line by line.
    """
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")


def _entry_from_matrix(m) -> dict:
    """One indicator's registry record, from its metadata."""
    dims = [{"label": d.label.strip(), "role": d.role,
             "n_options": len(d.options), "dim_code": d.dim_code}
            for d in m.dimensions]
    cells_needed = 1
    for d in m.dimensions:
        cells_needed *= len(d.options)

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
        "total_cells": cells_needed if m.dimensions else 0,
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
    localities = max(terr, key=lambda d: d.get("n_options") or 0)
    rest = [d for d in terr if d is not localities]
    return rest[0] if rest else None


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
    cells_needed = entry.get("total_cells") or 0

    # the finest REAL level is what counts, and if there is none, get() applies
    # no territorial filter. The same rule names a dimension's finest_level
    plan = {
        "default_level": territory.finest_level(levels),
        "tidy_ready": any(d.get("role") in ("teritoriu", "timp") for d in dims),
    }

    if not dims or cells_needed <= MAX_CELLS:
        plan["strategy"] = "single"
        plan["est_requests"] = 1
        return plan

    counties = (_county_dim(entry)
              if entry.get("family") == "judet_localitate" else None)
    if counties:
        plan["strategy"] = "by_county"
        plan["est_requests"] = counties.get("n_options") or 1
        return plan

    # over the threshold with no county plus locality pair: split on the
    # largest dimension, so each request fits under the threshold
    largest = max(dims, key=lambda d: d.get("n_options") or 0)
    n = largest.get("n_options") or 1
    per_option = max(1, cells_needed // n)
    per_request = max(1, MAX_CELLS // per_option)
    plan["strategy"] = f"split:{largest.get('label', '')}"
    plan["est_requests"] = -(-n // per_request)
    return plan


def refresh_plans(path: pathlib.Path | None = None, progress: bool = True) -> dict:
    """Recompute fetch_plan for the whole registry, with no network."""
    path = path or REGISTRY_PATH
    data = load_registry(path)
    if not data:
        print("There is no registry.json. Run schemas.build_registry().")
        return {}
    for e in data["entries"].values():
        if e.get("status") == "ok":
            e["fetch_plan"] = plan_for(e)
    _save(data, path)
    if progress:
        from collections import Counter
        strategies = Counter(
            (e.get("fetch_plan") or {}).get("strategy", "").split(":")[0]
            for e in data["entries"].values() if e.get("status") == "ok")
        print(f"plans recomputed: {dict(strategies)}")
    return data


_VALIDATION_FIELDS = ("validation", "validated_at", "validated_version",
                      "slice_cells")


def _keep_validation(old: dict | None, fresh: dict) -> dict:
    """Carry validation forward across a rebuild of the record.

    A rebuild recomputes the shape of the indicator, but it does not
    invalidate a check made against real data, as long as INS has not updated
    it meanwhile. If last_updated changed, the old validation is dropped and
    resume will redo it.
    """
    if not old or old.get("last_updated") != fresh.get("last_updated"):
        return fresh
    for field in _VALIDATION_FIELDS:
        if field in old:
            fresh[field] = old[field]
    return fresh


def _uncached(codes_wanted) -> list[str]:
    """The codes whose metadata is NOT in the disk cache."""
    return [c for c in codes_wanted
            if not client._cache_path(endpoints.matrix(c)).exists()]


def _ask(call_count: int) -> bool:
    minutes = max(1, round(call_count * SECUNDE_PER_APEL / 60))
    print(f"The build needs {call_count} uncached metadata records,")
    print(f"about {minutes} minutes of network. The rest come from cache.")
    try:
        answer = input("Build the registry now? [y/N] ")
    except (EOFError, OSError):
        return False
    return answer.strip().lower() in ("y", "yes", "d", "da")


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
    previous = {}
    if not refresh:
        existent = load_registry(path)
        if existent:
            previous = existent.get("entries", {})

    rows = catalog.load_index()
    todo = [r["code"] for r in rows]
    if incremental and not refresh:
        todo = [c for c in todo
                    if previous.get(c, {}).get("status") != "ok"]

    if confirm and todo:
        missing = todo if refresh else _uncached(todo)
        if missing and not _ask(len(missing)):
            print("Fine, not building. The registry stays as it was.")
            return {"registry_version": REGISTRY_VERSION, "entries": previous}

    entries = dict(previous)
    total = len(todo)
    for i, cod in enumerate(todo, 1):
        try:
            fresh = _entry_from_matrix(fetch_matrix(cod, refresh=refresh))
            entries[cod] = _keep_validation(previous.get(cod), fresh)
        except Exception as e:
            entries[cod] = {"name": "", "status": f"error: {e}",
                            "family": "alt", "dims": [], "levels": [],
                            "total_cells": 0}
        if progress and (i % 10 == 0 or i == total):
            print(f"\rbuilding the registry: {i}/{total}", end="", flush=True)
    if progress and total:
        print()

    data = {"registry_version": REGISTRY_VERSION, "entries": entries}
    _save(data, path)
    if progress:
        print(f"registry saved to {path}, {len(entries)} indicators")
        report(data)
    return data


def report(data: dict | None = None, path: pathlib.Path | None = None) -> None:
    """Reprint the census from the registry, without rebuilding."""
    data = data or load_registry(path)
    if not data:
        print("There is no registry.json. Run schemas.build_registry().")
        return

    entries = data.get("entries", {})
    total = len(entries)
    print(f"\nRegistry, version {data.get('registry_version')}: "
          f"{total} indicators")

    print("\nfamilies")
    for fam in FAMILIES:
        n = sum(1 for e in entries.values() if e.get("family") == fam)
        if n:
            print(f"  {fam:20} {n:5}  {100.0 * n / total:5.1f}%")

    print("\ndomains")
    domains_seen = {}
    for e in entries.values():
        domains_seen[e.get("domain") or "(no domain)"] = domains_seen.get(
            e.get("domain") or "(no domain)", 0) + 1
    for name, n in sorted(domains_seen.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  {name[:70]}")

    with_siruta = sum(1 for e in entries.values() if e.get("has_siruta"))
    large = [c for c, e in entries.items()
            if (e.get("total_cells") or 0) > MAX_CELLS]
    print(f"\nwith SIRUTA        : {with_siruta}")
    print(f"over {MAX_CELLS} cells : {len(large)} (these need splitting)")

    errors = {c: e["status"] for c, e in entries.items()
             if e.get("status") != "ok"}
    others = [c for c, e in entries.items()
              if e.get("family") == "alt" and c not in errors]
    print(f"\nfamily 'alt'       : {len(others)}")
    for c in others:
        e = entries[c]
        print(f"  {c:10} {len(e.get('dims') or [])} dimensions, "
              f"{e.get('name', '')[:60]}")
    print(f"errors             : {len(errors)}")
    for c, reason in errors.items():
        print(f"  {c:10} {reason[:90]}")


def registry_as_index(path: pathlib.Path | None = None) -> dict | None:
    """The registry, in the shape the search filters read.

    A gentle migration: search prefers the registry, but carries on with the
    older data/levels_index.json if the registry is missing.
    """
    data = load_registry(path)
    if not data:
        return None
    return {
        cod: {"levels": e.get("levels") or [],
              "periodicity": e.get("periodicity") or [],
              "has_caen": bool(e.get("has_caen")),
              "domain": e.get("domain") or ""}
        for cod, e in data.get("entries", {}).items()
        if e.get("status") == "ok"
    }
