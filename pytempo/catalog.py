"""Indexul de matrice (dicționarul de nume), căutarea și arborele de domenii.

search / find: fără fuzzy și fără filtru pe nivel deocamdată.

Cost: load_index e un singur apel, cache-uit. domains e tot un singur apel.
overview NU aduce metadatele indicatorilor: ar fi mii de apeluri.
"""
from . import client, endpoints, territory
from .matrix import Matrix, MatrixList, _clean, matrix
from .models import Node

_INDEX = None


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


def search(query: str, level: str | None = None, fuzzy: bool = False,
           limit: int = 25) -> MatrixList:
    """Caută indicatori după cuvânt cheie, în nume sau cod.

    query : unul sau mai multe cuvinte; se potrivesc TOATE (în nume sau cod),
            fără diacritice, insensibil la majuscule.
    limit : numărul maxim de rezultate.
    level : păstrează doar indicatorii care au acel nivel teritorial.
            ATENȚIE la cost: nivelele se știu doar din metadate, deci filtrul
            aduce metadatele potrivirilor, un apel pe rând, până adună limit
            rezultate. Fără level, răspunsul vine doar din indexul de nume.
    fuzzy : potrivire aproximativă. NEIMPLEMENTATĂ.
    """
    if fuzzy:
        raise NotImplementedError("fuzzy: neimplementat (deocamdata fuzzy=False)")
    if level is not None and level not in territory._LEVEL_ORDER:
        raise ValueError(
            f"Nivel necunoscut: {level!r}. "
            f"Disponibile: {list(territory._LEVEL_ORDER)}.")

    tokens = [_norm(t) for t in query.split()]
    out = []
    for row in load_index():
        hay = _norm(row["name"] + " " + row["code"])
        if not all(tok in hay for tok in tokens):
            continue

        if level is None:
            out.append(Matrix(code=row["code"], name=row["name"]))
        else:
            # aici se plateste: un GET de metadate per potrivire
            try:
                m = matrix(row["code"])
            except Exception:
                continue
            if level in m.levels:
                out.append(m)

        if len(out) >= limit:
            break
    return MatrixList(out)


def find(query: str, level: str | None = None, limit: int = 25) -> MatrixList:
    """Numele prietenos al căutării: t.find('salariati')."""
    return search(query, level=level, limit=limit)


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
