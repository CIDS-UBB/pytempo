"""Indexul de matrice (dicționarul de nume), căutarea și arborele de domenii.

Două indexuri, cu costuri foarte diferite:

Indexul de nume, load_index, e un singur apel cache-uit. Din el răspund
instant search, find și overview.

Indexul de nivele, build_index, cere metadatele fiecărui indicator, adică un
apel pe rând pentru tot catalogul. Se construiește o singură dată, se salvează
pe disc, iar după aceea filtrul pe nivel din find e instant. Fiindcă e scump,
construcția întreabă întâi userul.
"""
import json
import sys

from . import client, endpoints, territory
from .matrix import Matrix, MatrixList, _clean, matrix
from .models import Node

_INDEX = None

# fisierul indexului de nivele, langa cache-ul de raspunsuri brute
INDEX_FILE = "levels_index.json"


def load_index(refresh: bool = False) -> list[dict]:
    """Lista întreagă de indicatori: [{code, name}, ...] din matrix/matrices.

    Se cache-uiește în memorie și pe disc. refresh=True forțează re-descărcarea.
    """
    global _INDEX
    if _INDEX is None or refresh:
        data = client.get_json(endpoints.matrices(), use_cache=not refresh)
        _INDEX = [{"code": row["code"], "name": row["name"]} for row in data]
    return _INDEX


def name_dict(refresh: bool = False) -> dict[str, str]:
    """Dicționarul de nume: {cod: nume} pentru toți indicatorii."""
    return {row["code"]: row["name"] for row in load_index(refresh=refresh)}


def search(query: str = "", level: str | None = None, fuzzy: bool = False,
           limit: int | None = None) -> MatrixList:
    """Descoperire cu filtre. Pentru căutarea simplă pe nume, vezi find.

    query : unul sau mai multe cuvinte; se potrivesc TOATE (în nume sau cod),
            fără diacritice, insensibil la majuscule. Poate lipsi: cu query
            gol, filtrele lucrează peste tot catalogul.
    limit : implicit None, adică toate potrivirile. Rezultatul e o listă, deci
            poți tăia și singur cu slicing.
    level : păstrează doar indicatorii care au acel nivel teritorial. Filtrează
            din indexul local de nivele, instant. Dacă indexul nu există, te
            întreabă întâi dacă să îl construiască.
    fuzzy : potrivire aproximativă. NEIMPLEMENTATĂ.
    """
    if fuzzy:
        raise NotImplementedError("fuzzy: neimplementat (deocamdata fuzzy=False)")
    if level is not None and level not in territory._LEVEL_ORDER:
        raise ValueError(
            f"Nivel necunoscut: {level!r}. "
            f"Disponibile: {list(territory._LEVEL_ORDER)}.")

    tokens = [_norm(t) for t in query.split()]
    potriviri = [row for row in load_index()
                 if all(tok in _norm(row["name"] + " " + row["code"])
                        for tok in tokens)]

    if level is not None:
        nivele = load_levels_index()
        if nivele is None:
            nivele = build_index(confirm=True)
        if nivele is None:
            print("Fara indexul de nivele nu pot filtra. "
                  "Ruleaza t.build_index() cand ai cateva minute.")
            return MatrixList([])
        potriviri = [row for row in potriviri
                     if level in (nivele.get(row["code"], {}).get("levels") or [])]

    out = [Matrix(code=row["code"], name=row["name"]) for row in potriviri]
    if limit is not None:
        out = out[:limit]
    return MatrixList(out)


def find(query: str, limit: int | None = None) -> MatrixList:
    """Căutarea simplă pe nume: t.find('salariati').

    Fără filtre, deci răspunde instant din indexul de nume. Când vrei să
    filtrezi, ex. doar indicatorii care coboară la localitate, folosește
    search(query, level='localitate').
    """
    return search(query, limit=limit)


def _index_path():
    """Calea indexului de nivele, derivată din convenția de cache."""
    return client.CACHE_DIR.parent / INDEX_FILE


def load_levels_index() -> dict | None:
    """Indexul de nivele de pe disc, sau None dacă nu a fost construit."""
    path = _index_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ask_to_build(total: int) -> bool:
    """Întreabă o singură dată, clar, înainte de o construcție scumpă."""
    # 0.40s per apel, masurat pe INS; de aici estimarea
    minute = max(1, round(total * 0.4 / 60))
    print("Indexul de nivele nu exista inca.")
    print(f"Constructia cere metadatele fiecarui indicator: {total} apeluri,")
    print(f"in jur de {minute} minute prima data. Apoi filtrele pe nivel sunt")
    print("instant, fiindca indexul se salveaza pe disc si se refoloseste.")
    try:
        raspuns = input("Construiesc indexul acum? [d/N] ")
    except (EOFError, OSError):
        return False
    return raspuns.strip().lower() in ("d", "da", "y", "yes")


def build_index(progress: bool = True, refresh: bool = False,
                confirm: bool = True) -> dict | None:
    """Construiește indexul local de metadate: {cod: {levels: [...]}}.

    O singură dată, câteva minute, apoi filtrele pe metadate sunt instant.
    Un indicator care dă eroare la metadate e sărit și notat, nu oprește
    construcția. Întoarce None dacă userul refuză.
    """
    path = _index_path()
    if path.exists() and not refresh:
        return load_levels_index()

    randuri = load_index()
    total = len(randuri)
    if confirm and not _ask_to_build(total):
        print("Bine, nu construiesc. Filtrul pe nivel are nevoie de index; "
              "poti rula t.build_index() oricand.")
        return None

    index = {}
    sarite = []
    for i, row in enumerate(randuri, 1):
        cod = row["code"]
        try:
            index[cod] = {"levels": matrix(cod).levels}
        except Exception:
            sarite.append(cod)
        if progress and (i % 10 == 0 or i == total):
            print(f"\rconstruiesc indexul: {i}/{total}", end="", flush=True)
    if progress:
        print()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    if progress:
        print(f"index salvat in {path}, {len(index)} indicatori"
              + (f", {len(sarite)} sarite: {sarite[:5]}" if sarite else ""))
    return index


def domains() -> MatrixList:
    """Domeniile statistice de sus (A ... H), dintr-un singur apel.

    context('') întoarce tot arborele aplatizat; cele de sus au level 0.
    """
    tree = client.get_json(endpoints.context("")) or []
    out = [
        Node(code=row["context"]["code"], name=_clean(row["context"]["name"]))
        for row in tree if row.get("level") == 0
    ]
    # API-ul le da neordonat (H inaintea lui G); numele incep cu A. ... H.
    out.sort(key=lambda nod: nod.name)
    return MatrixList(out)


def overview() -> None:
    """Panorama ieftină: cât e catalogul și de unde începi.

    Două apeluri, amândouă cache-uite. Nu atinge metadatele indicatorilor.
    """
    n = len(load_index())
    doms = domains()
    print(f"pytempo: {n} indicatori TEMPO, in {len(doms)} domenii de sus.")
    print("Incepe cu find('salariati') sau domains(). t.help() da ghidul complet.")


def _norm(s: str) -> str:
    """Minuscule, fără diacritice, ca 'șomeri' să prindă 'Somerii'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return s.lower().translate(repl)
