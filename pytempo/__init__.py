"""pytempo: acces simplu la datele INS TEMPO Online.

Punctul de plecare e t.help(), care listează ce se poate face acum.
Descoperire (find, domains, overview), înțelegere (matrix, info, show, where,
related, levels, options) și tragerea datelor (get, cu filtru pe nivel).
"""
from .catalog import domains, find, load_index, name_dict, overview, search
from .matrix import Matrix, MatrixList, get, info, matrix
from .explore import init, browse

__version__ = "0.8.0"
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
  m.levels                     nivele, ex. ['national', 'judet', 'localitate']
  m.has_siruta                 True daca localitatile poarta prefix SIRUTA
  m.options('teritoriu')       ce valori are o dimensiune (index, rol sau label)
  m.help()                     acest ghid, dar pentru un indicator

TRAGI datele
  df = m.get()                 toate datele, ca DataFrame in format lung
  m.get(level='judet')         doar un nivel teritorial
  m.get(levels=['judet','regiune'])   mai multe nivele
  m.get(tidy=True)             plus coloane derivate: SIRUTA, nivel, tip, an
  m.get(progress=True)         spune cat s-a tras, la matricele mari
  t.get('FOM101A')             acelasi lucru, pornind de la cod

Datele vin rare: combinatiile fara date lipsesc ca randuri intregi, nu ca
valori goale. Filtrul pe nivel merge pe matricele cu o singura dimensiune
teritoriala, cazul obisnuit. Matricele care nu incap intr-un singur POST, ca
FOM104D, se descarca automat judet cu judet si se concateneaza; cele prea mari
care nu au localitati dupa care sa fie sparte se opresc cu un mesaj clar.
tidy=True doar adauga coloane, nu sterge si nu rearanjeaza nimic: denumirea
originala ramane, cu prefixul SIRUTA cu tot.

Listele intoarse de find, domains si related se afiseaza ca tabel si au
.recent(n), care ordoneaza dupa ultima actualizare doar elementele din set.""")
