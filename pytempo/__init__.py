"""pytempo: acces simplu la datele INS TEMPO Online.

Implementat acum:
    load_index()                              lista întreagă de indicatori [{code,name}]
    name_dict()                               dicționarul {cod: nume}
    search(query, fuzzy=False)                caută după cuvânt cheie (nume sau cod)
    matrix(cod)                               metadatele unui indicator
    matrix(cod).levels, .has_siruta           nivele teritoriale + prefix SIRUTA
    info(cod)                                 metadatele, ca dicționar

Vine mai târziu:
    matrix(cod).get(level=...)                date, cu filtru     (iterația 3)
    browse(), init()                          explorare           (iterația 4)
"""
from .catalog import load_index, name_dict, search
from .matrix import matrix, info, get
from .explore import init, browse

__version__ = "0.2.0"
__all__ = [
    "load_index", "name_dict", "search",
    "matrix", "info", "get",
    "init", "browse",
    "__version__",
]
