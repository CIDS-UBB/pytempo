"""pytempo: acces simplu la datele INS TEMPO Online.

Punctul de plecare e t.help(), care listează ce se poate face acum.
Descoperire (find, domains, overview), înțelegere (matrix, info, show, where,
related, levels, options). Datele propriu-zise vin la iterația 3.
"""
from .catalog import domains, find, load_index, name_dict, overview, search
from .matrix import Matrix, MatrixList, get, info, matrix
from .explore import init, browse

__version__ = "0.4.1"
__all__ = [
    "load_index", "name_dict", "search", "find", "domains", "overview",
    "matrix", "info", "get",
    "Matrix", "MatrixList",
    "init", "browse",
    "help",
    "__version__",
]


def help() -> None:
    """Ghid de navigare: ce metode există acum, grupate pe intenție."""
    print("""pytempo, ghid de navigare. Importa cu: import pytempo as t

GASESTI un indicator
  t.find('salariati')          cauta dupa cuvinte, in nume sau cod
  t.search('someri', limit=5)  acelasi lucru, numele lung
  t.domains()                  cele 8 domenii statistice de sus
  t.overview()                 cat e catalogul si de unde incepi

INTELEGI un indicator
  m = t.matrix('FOM104D')      aduce metadatele
  m.show()                     rezumat citibil: domeniu, nivele, dimensiuni
  t.info('FOM104D')            aceleasi metadate, ca dictionar
  m.where()                    breadcrumb-ul de domeniu
  m.related()                  ceilalti indicatori din acelasi nod
  m.levels                     nivelele teritoriale, ex. ['judet', 'localitate']
  m.has_siruta                 True daca localitatile poarta prefix SIRUTA
  m.options('Judete')          ce valori are o dimensiune
  m.help()                     acest ghid, dar pentru un indicator

Listele intoarse de find, domains si related se afiseaza ca tabel si au
.recent(n), care ordoneaza dupa ultima actualizare doar elementele din set.""")
