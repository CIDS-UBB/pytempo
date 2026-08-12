"""Indexul de matrice (dicționarul de nume) și căutarea în el.

load_index / name_dict / search: IMPLEMENTATE (iterația 1), fără fuzzy și fără
filtru pe nivel deocamdată. Filtrul pe nivel vine la iterația 2, fuzzy după.
"""
from . import client, endpoints
from .matrix import Matrix

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
           limit: int = 25) -> list[Matrix]:
    """Caută indicatori după cuvânt cheie, în nume sau cod.

    query : unul sau mai multe cuvinte; se potrivesc TOATE (în nume sau cod),
            fără diacritice, insensibil la majuscule.
    limit : numărul maxim de rezultate.
    level : filtru pe nivel teritorial. NEIMPLEMENTAT încă (iterația 2).
    fuzzy : potrivire aproximativă. NEIMPLEMENTAT încă (după iterația 2).
    """
    if fuzzy:
        raise NotImplementedError("fuzzy: iterație viitoare (deocamdată fuzzy=False)")
    if level is not None:
        raise NotImplementedError("filtru pe nivel: iterația 2")

    tokens = [_norm(t) for t in query.split()]
    out = []
    for row in load_index():
        hay = _norm(row["name"] + " " + row["code"])
        if all(tok in hay for tok in tokens):
            out.append(Matrix(code=row["code"], name=row["name"]))
        if len(out) >= limit:
            break
    return out


def _norm(s: str) -> str:
    """Minuscule, fără diacritice, ca 'șomeri' să prindă 'Somerii'."""
    repl = str.maketrans("ăâîșşțţ", "aaisstt")
    return s.lower().translate(repl)
