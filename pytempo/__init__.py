"""pytempo: acces simplu la datele INS TEMPO Online.

Punctul de plecare e t.help(), care listează ce se poate face acum.
Descoperire (find, domains, overview), înțelegere (matrix, info, show, where,
related, levels, options) și tragerea datelor (get, cu filtru pe nivel).
"""
from .catalog import (build_index, domains, find, load_index, name_dict,
                      overview, search)
from .matrix import Matrix, MatrixList, get, info, matrix
from .explore import init, browse

__version__ = "0.11.0"
__all__ = [
    "load_index", "name_dict", "search", "find", "domains", "overview",
    "build_index",
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
  t.find('salariati')          cautare simpla pe nume, instant
  t.search('salariati', level='localitate')   descoperire cu filtre
  t.search(level='localitate') filtrele merg si fara cuvant, peste tot catalogul
  t.build_index()              indexul de nivele, o data, cateva minute
  t.domains()                  cele 8 domenii statistice de sus
  t.overview()                 cat e catalogul si de unde incepi

INTELEGI un indicator
  m = t.matrix('FOM104D')      aduce metadatele
  m.show()                     rezumat scurt: domeniu, nivele, dimensiuni
  m.describe()                 fisa completa, cu tot textul de la INS
  m.options()                  ce dimensiuni are, cu rol si numar de optiuni
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

find si search sunt lucruri diferite. find e cautarea rapida pe nume, fara
filtre. search e descoperirea cu filtre, deocamdata level, si merge si fara
cuvant. Amandoua intorc TOATE potrivirile; taie cu slicing sau cu limit=N.

search(level=...) filtreaza din indexul local de nivele, deci e instant.
Indexul se construieste o singura data, cu t.build_index(): cere metadatele
fiecarui indicator, cateva minute, si se salveaza pe disc. Daca lipseste,
search te intreaba intai daca sa il construiasca.

Listele intoarse de find, domains si related se afiseaza ca tabel si au
.recent(n), care ordoneaza dupa ultima actualizare doar elementele din set.""")
