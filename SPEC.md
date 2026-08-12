# tempo-ins: bibliotecă Python pentru INS TEMPO Online

Instrucțiuni pentru Claude Code. Citește tot fișierul înainte de a scrie cod.
Contractul API e extras din codul real al bibliotecilor mark-veres/tempo.py și
RProjectRomania/TEMPO, care coincid. Nu improviza peste el.

## Ce este (și ce NU este)

ESTE: o bibliotecă open-source, mică, care extrage date din TEMPO. Un singur rol,
vorbește frumos cu API-ul INS. Se publică liber pe GitHub. Instalabilă cu
`pip install -e .`.

NU ESTE: bază de date, warehouse, enrichment SIRUTA, loader Postgres. Toate astea
trăiesc în proiecte SEPARATE, în aval, care importă biblioteca asta. Nucleul nu
are nicio opinie despre unde ajung datele și nicio dependință de bază de date.

## REGULA DE SIMPLITATE (obligatorie)

Pachet mic și plat. Fără async. Fără ierarhii de clase inutile, fără abstracții
premature, fără sisteme de plugin-uri, fără layere de „manager"/„factory". Dacă o
funcție se poate scrie simplu, se scrie simplu. Un agent de cod tinde să umfle;
nu umfla. 7 module, fiecare cu un rol clar (vezi mai jos). Atât.

## API public (forma dorită)

```python
import pytempo as t

# căutare după cuvânt cheie, în numele indicatorilor
t.search("șomeri")
# -> [Matrix(code="SOM101B", name="Șomerii înregistrați pe județe", levels=["judet"]), ...]

# filtru pe nivel: "șomeri la localități"
t.search("șomeri", level="localitate")

# metadatele complete
t.info("SOM101B")
# -> definiție, metodologie, observații, dimensiuni + opțiuni, nivele, periodicitate, ultima actualizare

# obiectul indicator; endpoint-ul e definit de cod
m = t.matrix("FOM104D")
m.levels          # ["judet", "localitate"]
m.dimensions

# date: fără filtru = tot; cu filtru = doar nivelele cerute
m.get()                              # toate datele
m.get(level="localitate")            # filtrat pe nivel
m.get(levels=["judet", "localitate"])
```

`t.get("FOM104D", level=...)` = scurtătură pentru `t.matrix("FOM104D").get(...)`.

Metode/valori: nume de metode în engleză (convenție pentru pachet public);
valorile de nivel în română, fiindcă sunt termeni INS: "national", "macroregiune",
"regiune", "judet", "localitate".

Tip de retur pentru date: pandas.DataFrame (implicit, dependință rezonabilă pentru
o bibliotecă de date), cu rânduri brute disponibile pentru cine nu vrea pandas.

## Contractul API TEMPO (autoritativ)

Bază: `http://statistici.insse.ro:8077/tempo-ins/`

### Index de matrice: GET matrix/matrices
Întoarce toate matricele cu cod + nume (ieftin, un apel). Baza pentru `search`.

### Metadate: GET matrix/{COD}
Chei exacte:
```
matrixName          str
ancestors[]         calea in context; ancestors[-1].code = parintele direct
definitie, metodologie, observatii, ultimaActualizare   str
periodicitati[], surseDeDate[]                          list
dimensionsMap[]     dimensiunile (VARIABIL de la un indicator la altul)
  - label           ex. "Judete", "Perioade", "Sexe", "Activitati CAEN"
  - dimCode         int
  - options[]
      - label       ex. "Cluj"
      - nomItemId   int   codul trimis in query
      - offset      int
      - parentId    int   leaga optiunea de parinte (localitate -> judet)
details{}           matMaxDim, matUMSpec, matRegJ, nomJud, nomLoc
```

### Date: POST pivot (intoarce CSV)
```
POST .../tempo-ins/pivot
{ "language":"ro", "encQuery":"<coduri>", "matCode":"<COD>",
  "matMaxDim":<details.matMaxDim>, "matUMSpec":<details.matUMSpec> }
```
`encQuery` = pe fiecare dimensiune, `nomItemId` separate prin virgulă; dimensiunile
separate prin `:`, IN ORDINEA din `dimensionsMap`. Ex: `"12,13:44:2020,2021"`.
Există și `matrix/dataSet/` (JSON); pivot (CSV) e calea probată de ambele biblioteci.

## Căi bine definite = future proof

TOATE URL-urile într-un singur modul `endpoints.py`. `BASE_URL` suprascriptibil
dintr-o variabilă de mediu (INS folosește portul ciudat 8077; dacă se schimbă,
modifici o linie). Nu hardcoda nicăieri altundeva un URL. Nu hardcoda poziții de
dimensiuni (citește din dimensionsMap) sau liste de județe (derivă din parentId).

Endpoint-uri (din pachetul R, confirmate):
```
BASE      http://statistici.insse.ro:8077/tempo-ins/
context   {BASE}context/{code}
matrices  {BASE}matrix/matrices?lang=ro
matrix    {BASE}matrix/{COD}
pivot     {BASE}pivot            (POST, CSV)
dataSet   {BASE}matrix/dataSet/  (JSON, alternativă)
config    http://statistici.insse.ro:8077/tempo-online/assets/data/tempo-config.json
```

## Nivele (cinstit)

Nivelul e proprietate a opțiunilor din dimensiunea teritorială, nu a matricei.
O matrice (FOM104D) conține și județe, și localități, legate prin parentId.
- Construiește arborele din parentId. ADANCIMEA in arbore = nivelul. Adâncimea e
  mereu corectă (adevăr de structură).
- Eticheta ("judet", "localitate") e o mapare best-effort peste adâncime, fiindcă
  denumirile variază între matrice. Ține adâncimea ca sursă de adevăr, eticheta ca
  zahăr. Confirmă maparea pe date reale în spike.
- `levels` ale unei matrice = mulțimea nivelelor prezente în dimensiunea teritorială.
- Filtrul `get(level=...)` selectează opțiunile teritoriale de la acel nivel.

## Chunking (portat din R)

Când o dimensiune are peste ~300 de opțiuni (localitățile), sparge acea dimensiune
în grupuri de 100 de nomItemId, trimite POST-uri multiple la pivot, concatenează
CSV-urile. `details.matMaxDim` parametrizează limita. E mecanismul oficial, nu o
presupunere.

## search (eficient, fără abuz de apeluri)

- `search("șomeri")`: filtrează indexul matrix/matrices (cache) după nume. Ieftin.
- `search("șomeri", level=...)`: filtrează întâi pe nume (ieftin), apoi aduce
  metadatele DOAR pentru cele câteva potriviri și le păstrează pe cele cu acel
  nivel. NU aduce metadatele tuturor matricelor.
- `levels` pe un rezultat se populează leneș (lazy), din metadate, la cerere.

## Structură (7 module, plat)

```
pytempo/
├── __init__.py     # API public: search, matrix, info, get
├── endpoints.py    # TOATE URL-urile; BASE_URL suprascriptibil
├── client.py       # HTTP subțire: get_json, post_pivot; cache raw pe fișiere
├── catalog.py      # index matrix/matrices: fetch + search (nume, nivel)
├── matrix.py       # clasa Matrix: metadate, dimensions, levels, get(level=...)
├── territory.py    # arbore parentId, detecție nivel, grupare pe județ
├── chunking.py     # split dimensiune mare pe 100 (din R)
└── parse.py        # pivot CSV -> rânduri tidy / DataFrame
```

Dependințe: requests, pandas. Cache raw în `data/raw/` (fișiere, nu bază de date).
Fără requests_cache global (defectul din tempo.py). Fără em dash / en dash în cod,
comentarii, docstrings, README. Cratimele în cuvinte compuse sunt corecte.

## Proveniență

- mark-veres/tempo.py : REFERINȚĂ de formă API. Nu o baza. Evită: query pe etichetă
  fuzzy (folosește nomItemId), cache global la import, lipsa chunking.
- RProjectRomania/TEMPO (R) : PORTĂM chunking-ul și URL-urile exacte. Nu R ca limbaj.
- gov2-ro/tempo-ins-dump : ORACOL de validare (are date dumpuite; compară output-ul).

## Spike + iterații

0. Spike A pe FOM101B (mecanism: metadate -> encQuery -> pivot -> parsare).
   Spike B pe FOM104D (chunking pe 100, arborele parentId, maparea nivelelor).
1. endpoints.py + client.py + catalog.py: search pe nume funcțional.
2. matrix.py + territory.py: info(), levels, dimensions; detecție nivel din parentId.
3. chunking.py + parse.py: get() cu filtru pe nivel; get() fără filtru = tot.
4. Ambalare: pyproject.toml, README, exemple; repo public pe GitHub.

## Proiect separat (în aval, mai târziu)

Un repo diferit importă `pytempo`, adaugă enrichment SIRUTA și încarcă în
Postgres/SQLite. Schema de acolo e problema lui, nu a bibliotecii.

---

## Addendum: schelet extins (module noi, staged)

Scheletul are câteva module în plus față de nucleul de 7, ca să acomodeze viziunea,
DAR nu le facem pe toate deodată. Fiecare e stub cu semnătură + docstring clar.

Structura reală a scheletului:
```
pytempo/
├── __init__.py     # API public
├── endpoints.py    # TOATE URL-urile; BASE_URL suprascriptibil (IMPLEMENTAT)
├── models.py       # Option, Dimension (dataclasses) (IMPLEMENTAT)
├── client.py       # HTTP: get_json, post_pivot            (it. 1 / 3)
├── catalog.py      # index + search (nume, fuzzy, nivel)   (it. 1 / 2)
├── matrix.py       # Matrix: info(), levels, dimensions, get()  (it. 2 / 3)
├── territory.py    # arbore parentId, nivele, grupare județ (it. 2 / 3)
├── chunking.py     # split_options (IMPLEMENTAT) + encQuery (it. 3)
├── parse.py        # pivot CSV -> DataFrame                 (it. 3)
├── schema.py       # metadate -> DDL Postgres/SQLite        (it. 5)
├── explore.py      # browse(A/B/C/D) + init() interactiv    (it. 4)
└── ai.py           # VIITOR opțional: limbaj natural -> indicatori
```

Idei noi confirmate în schelet:
- schema.py produce DIRECT schema Postgres din metadate (funcție pură, fără driver).
  Un tabel per indicator, tipuri inferate din rolul dimensiunii, definițiile INS ca
  COMMENT ON. E puntea către proiectul din aval, fără să bage DB în bibliotecă.
- explore.init() = explorator interactiv (meniu peste browse + search). UI viitor;
  motorul (browse, search) e ce contează.
- catalog.search(fuzzy=True) folosește difflib (stdlib), fără dependință nouă.
- ai.discover() = seam izolat pentru mod AI. Nucleul merge complet fără el.

Ordinea rămâne: întâi spike (FOM101B, apoi FOM104D), apoi iterațiile 1-3 (nucleul
util), apoi 4 (explorare), 5 (schema), și abia la urmă, opțional, AI.
