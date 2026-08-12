"""pytempo: acces simplu la datele INS TEMPO Online.

Implementat acum (iterația 1): descoperirea.
    load_index()                              lista întreagă de indicatori [{code,name}]
    name_dict()                               dicționarul {cod: nume}
    search(query, fuzzy=False)                caută după cuvânt cheie (nume sau cod)

Vine mai târziu:
    info(cod), matrix(cod).levels             metadate + nivele  (iterația 2)
    matrix(cod).get(level=...)                date, cu filtru     (iterația 3)
    browse(), init()                          explorare           (iterația 4)
"""
from .catalog import load_index, name_dict, search
from .matrix import matrix, info, get
from .explore import init, browse

__version__ = "0.1.0"
__all__ = [
    "load_index", "name_dict", "search",
    "matrix", "info", "get",
    "init", "browse",
    "__version__",
]
