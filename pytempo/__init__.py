"""pytempo: acces simplu la datele INS TEMPO Online.

Punctul de plecare e t.help(), care listează ce se poate face acum.
Descoperire (find, domains, overview), înțelegere (matrix, info, show, where,
related, levels, options) și tragerea datelor (get, cu filtru pe nivel).
"""
from .catalog import (build_index, domains, filters, find, load_index,
                      name_dict, overview, search)
from .matrix import Matrix, MatrixList, get, info, matrix
from .explore import init, browse

__version__ = "0.15.0"
__all__ = [
    "load_index", "name_dict", "search", "find", "domains", "overview",
    "build_index", "filters",
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
  t.filters()                  ce filtre are search si ce valori accepta
  t.build_index()              indexul de metadate, o data, cateva minute
  t.domains()                  cele 8 domenii statistice de sus
  t.overview()                 cat e catalogul si de unde incepi

DESCOPERIRE CU FILTRE, toate optionale si combinabile
  level='judet'                nivel teritorial
  caen=True                    doar cei cu dimensiune CAEN (False doar cei fara)
  domeniu='economic'           subsir din numele domeniului
  periodicitate='lunar'        subsir din periodicitate
  t.search(domeniu='economic', periodicitate='lunar', level='judet')

INTELEGI un indicator
  m = t.matrix('FOM104D')      aduce metadatele
  m.what()                     ce masoara, pe scurt: definitie, UM, cat de des
  m.where()                    unde sta si ce acopera: domeniu, teritoriu, ani
  m.how()                      manualul lui de descarcare, gata de copiat
  m.show()                     rezumat scurt: domeniu, nivele, dimensiuni
  m.describe()                 fisa completa, cu tot textul de la INS
  m.options()                  ce dimensiuni are, cu rol si numar de optiuni
  t.info('FOM104D')            aceleasi metadate, ca dictionar
  m.related()                  ceilalti indicatori din acelasi nod
  m.levels                     nivele, ex. ['national', 'judet', 'localitate']
  m.has_siruta                 True daca localitatile poarta prefix SIRUTA
  m.options('teritoriu')       ce valori are o dimensiune (index, rol sau label)
  m.help()                     acest ghid, dar pentru un indicator

TRAGI datele
  df = m.get()                 nivelul cel mai fin, curatat, cu progres
  m.get(level='judet')         doar un nivel teritorial
  m.get(levels=['judet','regiune'])   mai multe nivele
  m.get(level=None)            toate nivelele la un loc, vechiul implicit
  m.get(raw=True)              exact ce da INS, fara coloane derivate
  t.get('FOM101A')             acelasi lucru, pornind de la cod

get() executa planul din registry: citeste strategia, o ruleaza, aplica tidy.
Implicit ia cel mai fin nivel pe care il are indicatorul si spune intr-o linie
ce a hotarat. Cine nu are un nivel util, ca neteritorialii, primeste tot.

Datele vin rare: combinatiile fara date lipsesc ca randuri intregi, nu ca
valori goale. Matricele care nu incap intr-un singur POST se descarca in mai
multe cereri si se concateneaza: judet cu judet la cele cu localitati, altfel
pe cea mai mare dimensiune. Peste 50 de cereri get() intreaba intai; pune
confirm=False in scripturi. tidy nu sterge si nu rearanjeaza nimic: denumirea
originala ramane, cu prefixul SIRUTA cu tot.

find si search sunt lucruri diferite. find e cautarea rapida pe nume, fara
filtre. search e descoperirea cu filtre, si merge si fara cuvant. Amandoua
intorc TOATE potrivirile; taie cu slicing sau cu limit=N.

Filtrele pe metadate se rezolva din indexul local, deci sunt instant. Indexul
se construieste o singura data, cu t.build_index(): cere metadatele fiecarui
indicator, cateva minute, si se salveaza pe disc. Daca lipseste, search te
intreaba intai daca sa il construiasca.

Listele intoarse de find, domains si related se afiseaza ca tabel si au
.recent(n), care ordoneaza dupa ultima actualizare doar elementele din set.
Tabelul arata si coloana nivele, dar doar cand toate elementele o au deja,
adica la rezultatele lui search cu filtre. Afisarea nu costa niciodata un
apel de retea.""")
