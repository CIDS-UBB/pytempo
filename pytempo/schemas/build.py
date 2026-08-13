"""Construirea registrului de scheme: recensământul intern al catalogului.

registry.json stă în pachet și e versionat în repo, ca oricine clonează să
aibă deja harta catalogului fără să aștepte o construcție de minute. Aducerea
metadatelor e și testul de endpoint: status ok înseamnă endpoint viu.

Nimic de aici nu e API public. Se folosește din dezvoltare:
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

# 0.40s per apel, masurat pe INS; de aici estimarea din confirmare
SECUNDE_PER_APEL = 0.4


def load_registry(path: pathlib.Path | None = None) -> dict | None:
    """Registrul de pe disc, sau None dacă nu există.

    Ridică ValueError la o versiune de schemă necunoscută, ca o migrare ratată
    să dea un mesaj clar în loc de un KeyError undeva mai încolo.
    """
    path = path or REGISTRY_PATH
    if not path.exists():
        return None
    date = json.loads(path.read_text(encoding="utf-8"))
    versiune = date.get("registry_version")
    if versiune != REGISTRY_VERSION:
        raise ValueError(
            f"registry.json are registry_version={versiune!r}, iar codul "
            f"asteapta {REGISTRY_VERSION}. Ruleaza "
            f"schemas.build_registry(refresh=True) ca sa il reconstruiesti.")
    return date


def _save(date: dict, path: pathlib.Path) -> None:
    """Scrie registrul canonic: chei sortate, un camp pe linie.

    Fișierul e versionat în repo, deci forma contează: sortarea îl face
    stabil între reconstrucții, iar indentarea face diff-ul citibil, ca o
    schimbare de la INS să se vadă rând cu rând.
    """
    path.write_text(
        json.dumps(date, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")


def _entry_from_matrix(m) -> dict:
    """Fișa de registry a unui indicator, din metadatele lui."""
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
    # curatam numele de domeniu de HTML-ul incorporat, ca peste tot
    from ..matrix import _clean
    entry["domain"] = _clean(entry["domain"])
    entry["family"] = classify(entry)
    entry["fetch_plan"] = plan_for(entry)
    return entry


def _county_dim(entry: dict) -> dict | None:
    """Dimensiunea de județe a unui indicator cu localități, dacă are una.

    Nu toate au: TMP1173 are o singură dimensiune teritorială, statii de
    monitorizare, deci nu se poate sparge pe județ.
    """
    terr = [d for d in (entry.get("dims") or []) if d.get("role") == "teritoriu"]
    if len(terr) < 2:
        return None
    localitati = max(terr, key=lambda d: d.get("n_options") or 0)
    restul = [d for d in terr if d is not localitati]
    return restul[0] if restul else None


def plan_for(entry: dict) -> dict:
    """Planul de extragere al unui indicator, calculat din fișa lui.

    Get-ul final va fi un simplu executor al acestui plan: citește strategia,
    o execută, aplică tidy. Nicio decizie la runtime, niciun calcul de cost în
    momentul cererii.

    strategy: 'single' sub prag; 'by_county' la matricele cu localități care
    au și o dimensiune de județe; 'split:<label>' altfel, pe dimensiunea cu
    cele mai multe opțiuni.
    """
    dims = entry.get("dims") or []
    levels = entry.get("levels") or []
    celule = entry.get("total_cells") or 0

    # 'necunoscut' nu e un nivel de cerut: denumirile care nu se incadreaza in
    # nomenclator nu formeaza o felie utila. Cel mai fin nivel REAL conteaza,
    # iar daca nu exista niciunul, get() nu filtreaza teritorial deloc.
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

    # peste prag si fara pereche judet plus localitate: se sparge pe cea mai
    # mare dimensiune, ca cererea sa incapa sub prag
    cea_mai_mare = max(dims, key=lambda d: d.get("n_options") or 0)
    n = cea_mai_mare.get("n_options") or 1
    pe_optiune = max(1, celule // n)
    pe_cerere = max(1, MAX_CELLS // pe_optiune)
    plan["strategy"] = f"split:{cea_mai_mare.get('label', '')}"
    plan["est_requests"] = -(-n // pe_cerere)
    return plan


def refresh_plans(path: pathlib.Path | None = None, progress: bool = True) -> dict:
    """Recalculează fetch_plan pentru tot registrul, fără rețea."""
    path = path or REGISTRY_PATH
    date = load_registry(path)
    if not date:
        print("Nu exista registry.json. Ruleaza schemas.build_registry().")
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
        print(f"planuri recalculate: {dict(strategii)}")
    return date


_VALIDATION_FIELDS = ("validation", "validated_at", "validated_version",
                      "slice_cells")


def _keep_validation(veche: dict | None, noua: dict) -> dict:
    """Duce validarea mai departe peste o reconstrucție a fișei.

    O reconstrucție recalculează forma indicatorului, dar nu invalidează o
    verificare făcută pe date reale, atâta timp cât INS nu l-a actualizat
    între timp. Dacă last_updated s-a schimbat, validarea veche pică, iar
    resume o va relua.
    """
    if not veche or veche.get("last_updated") != noua.get("last_updated"):
        return noua
    for camp in _VALIDATION_FIELDS:
        if camp in veche:
            noua[camp] = veche[camp]
    return noua


def _uncached(coduri) -> list[str]:
    """Codurile ale căror metadate NU sunt în cache-ul de disc."""
    return [c for c in coduri
            if not client._cache_path(endpoints.matrix(c)).exists()]


def _ask(nr_apeluri: int) -> bool:
    minute = max(1, round(nr_apeluri * SECUNDE_PER_APEL / 60))
    print(f"Constructia are nevoie de {nr_apeluri} metadate necache-uite,")
    print(f"adica in jur de {minute} minute de retea. Restul vin din cache.")
    try:
        raspuns = input("Construiesc registrul acum? [d/N] ")
    except (EOFError, OSError):
        return False
    return raspuns.strip().lower() in ("d", "da", "y", "yes")


def build_registry(progress: bool = True, refresh: bool = False,
                   incremental: bool = True, confirm: bool = True,
                   path: pathlib.Path | None = None) -> dict:
    """Recensământul catalogului: o fișă de registry per indicator.

    incremental=True păstrează intrările existente cu status ok și aduce doar
    codurile noi. Atenție: așa NU se văd schimbările făcute de INS la un
    indicator deja înregistrat, fiindcă nu îi recitim metadatele. Pentru asta
    e refresh=True, care reface tot, ocolind cache-ul de metadate.
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
            print("Bine, nu construiesc. Registrul ramane cum era.")
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
            print(f"\rconstruiesc registrul: {i}/{total}", end="", flush=True)
    if progress and total:
        print()

    date = {"registry_version": REGISTRY_VERSION, "entries": entries}
    _save(date, path)
    if progress:
        print(f"registru salvat in {path}, {len(entries)} indicatori")
        report(date)
    return date


def report(date: dict | None = None, path: pathlib.Path | None = None) -> None:
    """Reprintează recensământul din registru, fără reconstrucție."""
    date = date or load_registry(path)
    if not date:
        print("Nu exista registry.json. Ruleaza schemas.build_registry().")
        return

    entries = date.get("entries", {})
    total = len(entries)
    print(f"\nRegistru, versiune {date.get('registry_version')}: "
          f"{total} indicatori")

    print("\nfamilii")
    for fam in FAMILIES:
        n = sum(1 for e in entries.values() if e.get("family") == fam)
        if n:
            print(f"  {fam:20} {n:5}  {100.0 * n / total:5.1f}%")

    print("\ndomenii")
    domenii = {}
    for e in entries.values():
        domenii[e.get("domain") or "(fara domeniu)"] = domenii.get(
            e.get("domain") or "(fara domeniu)", 0) + 1
    for nume, n in sorted(domenii.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  {nume[:70]}")

    cu_siruta = sum(1 for e in entries.values() if e.get("has_siruta"))
    mari = [c for c, e in entries.items()
            if (e.get("total_cells") or 0) > MAX_CELLS]
    print(f"\ncu SIRUTA        : {cu_siruta}")
    print(f"peste {MAX_CELLS} celule: {len(mari)} (vor cere chunking)")

    erori = {c: e["status"] for c, e in entries.items()
             if e.get("status") != "ok"}
    altele = [c for c, e in entries.items()
              if e.get("family") == "alt" and c not in erori]
    print(f"\nfamilia 'alt'    : {len(altele)}")
    for c in altele:
        e = entries[c]
        print(f"  {c:10} {len(e.get('dims') or [])} dimensiuni, "
              f"{e.get('name', '')[:60]}")
    print(f"erori            : {len(erori)}")
    for c, motiv in erori.items():
        print(f"  {c:10} {motiv[:90]}")


def registry_as_index(path: pathlib.Path | None = None) -> dict | None:
    """Registrul, în forma pe care o citește filtrul din search.

    Migrare blândă: search preferă registrul, dar merge mai departe cu vechiul
    data/levels_index.json dacă registrul lipsește.
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
