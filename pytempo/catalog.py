"""The matrix index (the name dictionary), search, and the domain tree.

Two indexes, with very different costs:

The name index, load_index, is a single cached call. search, find and overview
answer from it instantly.

The metadata index, build_index, needs each indicator's metadata, which means
one call per code for the whole catalogue. It is built once, saved to disk, and
after that the metadata filters are instant. Because it is expensive, the build
asks the user first. Normally it is not needed at all: the schema registry ships
with the package and covers the same ground.
"""
import json

from . import client, endpoints, territory
from .matrix import Matrix, MatrixList, _clean, matrix
from .models import Node

_INDEX = None

# the metadata index file, next to the raw response cache
INDEX_FILE = "levels_index.json"

# the fields build_index writes; an older index may hold fewer, and filters on
# a missing field match nothing
INDEX_FIELDS = ("levels", "periodicity", "has_caen", "domain")


def load_index(refresh: bool = False) -> list[dict]:
    """Every indicator: [{code, name}, ...] from matrix/matrices.

    Cached in memory and on disk. refresh=True forces a re-download.
    """
    global _INDEX
    if _INDEX is None or refresh:
        data = client.get_json(endpoints.matrices(), use_cache=not refresh)
        _INDEX = [{"code": row["code"], "name": row["name"]} for row in data]
    return _INDEX


def name_dict(refresh: bool = False) -> dict[str, str]:
    """The name dictionary: {code: name} for every indicator."""
    return {row["code"]: row["name"] for row in load_index(refresh=refresh)}


def _passes_filters(record: dict, level, caen, domeniu, periodicitate) -> bool:
    """Does one indicator's index record pass every requested filter?"""
    if level is not None and level not in (record.get("levels") or []):
        return False
    if caen is not None and bool(record.get("has_caen")) is not bool(caen):
        return False
    if domeniu is not None and _norm(domeniu) not in _norm(record.get("domain") or ""):
        return False
    if periodicitate is not None:
        wanted_text = _norm(periodicitate)
        if not any(wanted_text in _norm(p) for p in (record.get("periodicity") or [])):
            return False
    return True


def search(query: str = "", level: territory.Level | None = None,
           caen: bool | None = None, domeniu: str | None = None,
           periodicitate: str | None = None, fuzzy: bool = False,
           limit: int | None = None) -> MatrixList:
    """Discovery with filters. For plain keyword search, see find.

    query : one or more words; ALL of them must match, in the name or the code,
            case insensitively and ignoring diacritics. It may be omitted: with
            an empty query the filters work across the whole catalogue.
    limit : None by default, meaning every match. The result is a list, so you
            can slice it yourself.

    The metadata filters combine with each other and with the query, and are
    resolved from the local index, so they are instant. See t.filters() for the
    accepted values.

    level        : territorial level, for example 'judet' or 'localitate'.
    caen         : True keeps only those with a CAEN dimension, False only those
                   without.
    domeniu      : substring of the domain name, for example 'economic'.
    periodicitate: substring of the periodicity, for example 'anual', 'lunar'.
    fuzzy        : approximate matching. NOT IMPLEMENTED.
    """
    if fuzzy:
        raise NotImplementedError("fuzzy matching is not implemented yet")
    if level is not None and level not in territory._LEVEL_ORDER:
        raise territory.level_error(level, territory._LEVEL_ORDER)

    tokens = [_norm(t) for t in query.split()]
    matches = [row for row in load_index()
                 if all(tok in _norm(row["name"] + " " + row["code"])
                        for tok in tokens)]

    needs_metadata = any(f is not None
                        for f in (level, caen, domeniu, periodicitate))
    levels_by_code = {}
    if needs_metadata:
        levels_by_code = load_levels_index()
        if levels_by_code is None:
            levels_by_code = build_index(confirm=True)
        if levels_by_code is None:
            print("Without the metadata index I cannot filter. "
                  "Run t.build_index() when you have a few minutes.")
            return MatrixList([])
        _warn_if_stale(levels_by_code)
        matches = [row for row in matches
                     if _passes_filters(levels_by_code.get(row["code"], {}), level,
                                        caen, domeniu, periodicitate)]

    out = []
    for row in matches:
        record = levels_by_code.get(row["code"], {})
        known_levels = record.get("levels") if needs_metadata else None
        out.append(Matrix(
            code=row["code"], name=row["name"],
            periodicity=list(record.get("periodicity") or []),
            cached_levels=None if known_levels is None else list(known_levels)))
    if limit is not None:
        out = out[:limit]
    return MatrixList(out)


def filters() -> None:
    """Which filters search accepts, and what values each one takes."""
    levels_by_code = load_levels_index()
    print("Filters for t.search(). They combine with each other and with the "
          "search words.")
    print(f"  level        : {list(territory._LEVEL_ORDER)}")
    print("  caen         : True only those with a CAEN dimension, False only "
          "those without")
    print("  domeniu      : substring of the domain name, diacritics ignored")
    for node in domains():
        print(f"                 {node.name}")
    if levels_by_code:
        seen = sorted({p for f in levels_by_code.values()
                         for p in (f.get("periodicity") or [])})
    else:
        seen = ["Anuala", "Lunara", "Trimestriala", "Semestriala"]
    print("  periodicitate: substring of the periodicity, diacritics ignored")
    print(f"                 {seen}")
    print()
    print("The metadata filters rest on the local index. If it is missing,")
    print("search asks first whether to build it (t.build_index()).")
    if not levels_by_code:
        print("There is no index yet, so the periodicities above are common")
        print("examples, not the real values from the catalogue.")
    print()
    print("Example:")
    print("  t.search(domeniu='economic', periodicitate='lunar', level='judet')")


def find(query: str, limit: int | None = None) -> MatrixList:
    """Plain keyword search: t.find('salariati').

    No filters, so it answers instantly from the name index. When you want to
    filter, for example only indicators that reach locality level, use
    search(query, level='localitate').
    """
    return search(query, limit=limit)


def _index_path():
    """Path of the metadata index, derived from the cache convention."""
    return client.CACHE_DIR.parent / INDEX_FILE


def load_levels_index() -> dict | None:
    """The source for metadata filters, or None if there is none.

    Prefers the schema registry, which ships with the package. If that is
    missing it falls back to the older data/levels_index.json built by
    build_index.
    """
    from . import schemas  # local import: schemas imports catalog, else a cycle

    try:
        from_registry = schemas.registry_as_index()
    except ValueError as e:
        print(f"The registry cannot be read: {e}")
        from_registry = None
    if from_registry:
        return from_registry

    path = _index_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _warn_if_stale(levels_by_code: dict) -> None:
    """An index built by an older version lacks the newer fields.

    The simple route, so we never start a multi minute rebuild out of nowhere:
    a missing field matches nothing, and the user is told how to fix it.
    """
    if not levels_by_code:
        return
    any_record = next(iter(levels_by_code.values()))
    missing_fields = [c for c in INDEX_FIELDS if c not in any_record]
    if missing_fields:
        print(f"The index comes from an older version and lacks {missing_fields}. "
              f"Filters on those fields will match nothing; "
              f"run t.build_index(refresh=True) to complete it.")


def _ask_to_build(total: int) -> bool:
    """Ask once, clearly, before an expensive build."""
    # 0.40s per call, measured against INS; that is where the estimate comes from
    minutes = max(1, round(total * 0.4 / 60))
    print("The metadata index does not exist yet.")
    print(f"Building it needs each indicator's metadata: {total} calls,")
    print(f"roughly {minutes} minutes the first time. After that the search")
    print("filters are instant, because the index is saved and reused.")
    try:
        answer = input("Build the index now? [y/N] ")
    except (EOFError, OSError):
        return False
    return answer.strip().lower() in ("y", "yes", "d", "da")


def build_index(progress: bool = True, refresh: bool = False,
                confirm: bool = True) -> dict | None:
    """Build the local metadata index: {code: {levels: [...], ...}}.

    Once, a few minutes, and then the metadata filters are instant. An
    indicator whose metadata fails is skipped and noted, it does not stop the
    build. Returns None if the user declines.
    """
    path = _index_path()
    if path.exists() and not refresh:
        return load_levels_index()

    rows = load_index()
    total = len(rows)
    if confirm and not _ask_to_build(total):
        print("Fine, not building. The level filter needs the index; "
              "you can run t.build_index() any time.")
        return None

    index = {}
    skipped = []
    for i, row in enumerate(rows, 1):
        cod = row["code"]
        try:
            m = matrix(cod)
            index[cod] = {
                "levels": m.levels,
                "periodicity": list(m.periodicity or []),
                "has_caen": any(d.role == "caen" for d in m.dimensions),
                "domain": _clean(m.ancestors[0]["name"]) if m.ancestors else "",
            }
        except Exception:
            skipped.append(cod)
        if progress and (i % 10 == 0 or i == total):
            print(f"\rbuilding the index: {i}/{total}", end="", flush=True)
    if progress:
        print()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    if progress:
        print(f"index saved to {path}, {len(index)} indicators"
              + (f", {len(skipped)} skipped: {skipped[:5]}" if skipped else ""))
    return index


def domains() -> MatrixList:
    """The top level statistical domains (A through H), in a single call.

    context('') returns the whole tree flattened; the top ones have level 0.
    """
    tree = client.get_json(endpoints.context("")) or []
    out = [
        Node(code=row["context"]["code"], name=_clean(row["context"]["name"]))
        for row in tree if row.get("level") == 0
    ]
    # the API returns them unordered (H before G); names start with A. ... H.
    out.sort(key=lambda node: node.name)
    return MatrixList(out)


def overview() -> None:
    """The cheap panorama: how big the catalogue is and where to start.

    Two calls, both cached. It does not touch indicator metadata.
    """
    n = len(load_index())
    doms = domains()
    print(f"pytempo: {n} TEMPO indicators, in {len(doms)} top level domains.")
    print("Start with find('salariati') or domains(). t.help() has the full guide.")


def _norm(s: str) -> str:
    """Lowercase and strip diacritics, so 'șomeri' matches 'Somerii'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return s.lower().translate(repl)
