"""Teste offline: import, API public, căutare pe un index injectat."""
import json

import pandas as pd

import pytempo as t
from pytempo import (catalog, chunking, client, endpoints, parse, schemas,
                     territory)
from pytempo.chunking import split_options
from pytempo.matrix import MAX_CELLS

# fixture dupa structura reala a lui FOM104D: doua dimensiuni teritoriale
# separate (Judete si Localitati), timp si unitate de masura.
FOM104D = {
    "matrixName": "Numarul mediu al salariatilor pe judete si localitati",
    "definitie": "Numarul mediu al salariatilor",
    "metodologie": "Cercetare statistica",
    "observatii": "",
    "ultimaActualizare": "20-11-2025",
    "periodicitati": ["Anuala"],
    "surseDeDate": [{"nume": "Cercetarea statistica privind costul fortei de munca"}],
    # numele de nod vin cu HTML incorporat, ca in API-ul real
    "ancestors": [
        {"name": "home", "code": ""},
        {"name": "A. STATISTICA SOCIALA", "code": "1"},
        {"name": 'FORTA DE MUNCA <a href="https://insse.ro/x">Comunicate</a>',
         "code": "15"},
        {"name": "SALARIATI", "code": "1513"},
    ],
    "details": {
        "nomJud": 1, "nomLoc": 2, "matTime": 3,
        "matCaen1": 0, "matCaen2": 0, "matRegJ": 0,
        "matSiruta": 1, "matMaxDim": 4,
    },
    "dimensionsMap": [
        {"dimCode": 1, "label": "Judete", "options": [
            {"label": "TOTAL", "nomItemId": 112, "offset": 1, "parentId": None},
            {"label": "Alba", "nomItemId": 3064, "offset": 2, "parentId": None},
        ]},
        {"dimCode": 2, "label": "Localitati ", "options": [
            {"label": "TOTAL", "nomItemId": 112, "offset": 0, "parentId": 112},
            {"label": "1017 MUNICIPIUL ALBA IULIA", "nomItemId": 113,
             "offset": 2, "parentId": 3064},
            {"label": "1026 ORAS ABRUD", "nomItemId": 114,
             "offset": 3, "parentId": 3064},
        ]},
        {"dimCode": 3, "label": "Ani", "options": [
            {"label": "Anul 1990", "nomItemId": 4247, "offset": 1, "parentId": None},
        ]},
        {"dimCode": 4, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 9685, "offset": 1, "parentId": None},
        ]},
    ],
}

# optiunile unei dimensiuni teritoriale ierarhice, ca in API-ul real:
# TOTAL, apoi macroregiuni, apoi regiuni, apoi judete
_IERARHIC = [
    {"label": "TOTAL", "nomItemId": 1, "offset": 1, "parentId": None},
    {"label": "MACROREGIUNEA UNU", "nomItemId": 2, "offset": 2, "parentId": 1},
    {"label": "Regiunea NORD-VEST", "nomItemId": 3, "offset": 3, "parentId": 2},
    {"label": "Bihor", "nomItemId": 4, "offset": 4, "parentId": 3},
    {"label": "Cluj", "nomItemId": 5, "offset": 5, "parentId": 3},
]

# SOM101B: nomJud si nomLoc sunt 0, dar matRegJ arata spre dimensiunea 3.
# Detectia vine din details.
SOM101B = {
    "matrixName": "Somerii inregistrati pe sexe, macroregiuni si judete",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "15-10-2025",
    "periodicitati": ["Anuala"],
    "surseDeDate": [],
    "ancestors": [
        {"name": "home", "code": ""},
        {"name": "A. STATISTICA SOCIALA", "code": "1"},
        {"name": "SOMAJ", "code": "1520"},
    ],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 4, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 3, "matMaxDim": 5},
    "dimensionsMap": [
        {"dimCode": 3, "label": "Macroregiuni, regiuni de dezvoltare si judete",
         "options": _IERARHIC},
        {"dimCode": 4, "label": "Ani", "options": [
            {"label": "Anul 2020", "nomItemId": 20, "offset": 1, "parentId": None}]},
        {"dimCode": 5, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 30, "offset": 1, "parentId": None}]},
    ],
}

# FOM101A: matRegJ = 2, deci tot din details. Fixture fidel realitatii.
FOM101A = {
    "matrixName": "Resurse de munca pe sexe, macroregiuni, regiuni de dezvoltare si judete",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "30-09-2025",
    "periodicitati": ["Anuala"],
    "surseDeDate": [],
    "ancestors": [{"name": "A. STATISTICA SOCIALA", "code": "1"}],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 3, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 2, "matMaxDim": 4,
                "matUMSpec": 0},
    "dimensionsMap": [
        {"dimCode": 1, "label": "Sexe", "options": [
            {"label": "Total", "nomItemId": 40, "offset": 1, "parentId": None}]},
        {"dimCode": 2, "label": "Macroregiuni, regiuni de dezvoltare si judete",
         "options": _IERARHIC},
        {"dimCode": 3, "label": "Ani", "options": [
            {"label": "Anul 2020", "nomItemId": 41, "offset": 1, "parentId": None}]},
        {"dimCode": 4, "label": "UM: Mii persoane", "options": [
            {"label": "Mii persoane", "nomItemId": 42, "offset": 1, "parentId": None}]},
    ],
}

# context('') e tot arborele aplatizat; domeniile de sus au level 0
CONTEXT_ROOT = [
    {"parentCode": "0", "level": 0,
     "context": {"code": "1", "name": "A. STATISTICA SOCIALA"}},
    {"parentCode": "0", "level": 0,
     "context": {"code": "2", "name": 'B. STATISTICA ECONOMICA <a href="x">y</a>'}},
    {"parentCode": "1", "level": 1,
     "context": {"code": "15", "name": "FORTA DE MUNCA"}},
    {"parentCode": "15", "level": 2,
     "context": {"code": "1513", "name": "SALARIATI"}},
]

# context(nod) e un dict; frunzele-matrice au url == 'matrix'
CONTEXT_1513 = {
    "context": {"code": "1513", "name": "SALARIATI"},
    "ancestors": [],
    "children": [
        {"code": "FOM104A", "name": "Numarul mediu al salariatilor pe CAEN",
         "url": "matrix"},
        {"code": "FOM104D", "name": "Numarul mediu al salariatilor pe judete si localitati",
         "url": "matrix"},
        {"code": "1514", "name": "SUBNOD OARECARE", "url": "context"},
    ],
}


def test_version():
    assert t.__version__


def test_public_api():
    for name in ("load_index", "name_dict", "search", "matrix", "info", "get"):
        assert hasattr(t, name)


def test_endpoints_overridable():
    assert "tempo-ins" in endpoints.BASE_URL
    assert endpoints.matrix("FOM104D").endswith("matrix/FOM104D")


def test_split_options():
    assert split_options([1, 2, 3, 4, 5], size=2) == [[1, 2], [3, 4], [5]]


def test_search_offline(monkeypatch):
    fake = [
        {"code": "FOM104D", "name": "Numarul mediu al salariatilor pe judete si localitati"},
        {"code": "SOM101B", "name": "Somerii inregistrati pe judete"},
        {"code": "POP105A", "name": "Populatia rezidenta"},
    ]
    monkeypatch.setattr(catalog, "_INDEX", fake)

    hits = t.search("FOM104D")
    assert len(hits) == 1 and hits[0].code == "FOM104D"
    assert hits[0].url.endswith("matrix/FOM104D")

    # diacritice: 'șomeri' prinde 'Somerii'
    hits = t.search("șomeri")
    assert any(m.code == "SOM101B" for m in hits)

    # doua cuvinte: toate trebuie sa se potriveasca
    hits = t.search("salariatilor localitati")
    assert len(hits) == 1 and hits[0].code == "FOM104D"


def _fake_index(monkeypatch,
                codes=("FOM104D", "SOM101B", "FOM101A", "FOM104F",
                       "TMP1173")):
    """Catalogul, injectat: matrix() verifica in el inainte de fetch."""
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": c} for c in codes])


def _fake_matrix(monkeypatch, data=FOM104D):
    """Injecteaza raspunsul matrix/{cod}. t.matrix e functia, nu modulul."""
    _fake_index(monkeypatch)
    monkeypatch.setattr(client, "get_json", lambda url, **kw: data)


def _fake_api(monkeypatch, extra=None):
    """Ruteaza dupa URL: matrix/{cod}, context('') si context(nod)."""
    _fake_index(monkeypatch)
    routes = {
        endpoints.matrix("FOM104D"): FOM104D,
        endpoints.matrix("SOM101B"): SOM101B,
        endpoints.matrix("FOM101A"): FOM101A,
        endpoints.context(""): CONTEXT_ROOT,
        endpoints.context("1513"): CONTEXT_1513,
    }
    routes.update(extra or {})

    def fake(url, **kw):
        if url not in routes:
            raise AssertionError(f"URL neasteptat in test: {url}")
        return routes[url]

    monkeypatch.setattr(client, "get_json", fake)


def test_roles_from_details(monkeypatch):
    _fake_matrix(monkeypatch)
    m = t.matrix("FOM104D")
    assert [d.role for d in m.dimensions] == [
        "teritoriu", "teritoriu", "timp", "um"]
    # dim_index pastreaza ordinea din dimensionsMap
    assert [d.dim_index for d in m.dimensions] == [0, 1, 2, 3]


# TMP1173: labelul zice 'Localitate', dar matSiruta e 0 si optiunile sunt
# statii de monitorizare, nu localitati cu prefix SIRUTA
TMP1173 = {
    "matrixName": "Niveluri medii anuale de particule in suspensie",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "01-06-2025",
    "periodicitati": ["Anuala"], "surseDeDate": [],
    "ancestors": [{"name": "E. MEDIU INCONJURATOR", "code": "5"}],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 3, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 0, "matMaxDim": 4,
                "matUMSpec": 0},
    "dimensionsMap": [
        {"dimCode": 1, "label": "Categorii de emisii", "options": [
            {"label": "Total", "nomItemId": 60, "offset": 1, "parentId": None}]},
        {"dimCode": 2,
         "label": "Statii de monitorizare de tip fond urban - Localitate",
         "options": [
             {"label": "AB-1 - Municipiul Alba Iulia", "nomItemId": 61,
              "offset": 1, "parentId": None},
             {"label": "BT-1 - Municipiul Botosani", "nomItemId": 62,
              "offset": 2, "parentId": None},
             {"label": "BV-2 - Municipiul Brasov", "nomItemId": 63,
              "offset": 3, "parentId": None}]},
        {"dimCode": 3, "label": "Ani", "options": [
            {"label": "Anul 2024", "nomItemId": 64, "offset": 1,
             "parentId": None}]},
        {"dimCode": 4, "label": "Unitati de masura", "options": [
            {"label": "Micrograme", "nomItemId": 65, "offset": 1,
             "parentId": None}]},
    ],
}


def test_station_dimension_is_not_localities(monkeypatch):
    """Labelul singur nu face o dimensiune de localitati."""
    _fake_api(monkeypatch, extra={endpoints.matrix("TMP1173"): TMP1173})
    m = t.matrix("TMP1173")
    statii = m.dimensions[1]
    assert statii.role == "teritoriu"          # ramane teritoriala
    assert territory.is_locality_dimension(statii, m.details) is False
    # nivelele vin din optiuni, nu din label
    assert m.levels == ["necunoscut"]
    assert territory.dimension_levels(statii, m.details) == {"necunoscut"}


def test_station_labels_are_not_counties(monkeypatch):
    _fake_api(monkeypatch, extra={endpoints.matrix("TMP1173"): TMP1173})
    m = t.matrix("TMP1173")
    tidy = parse.standardize(
        pd.DataFrame({
            "Categorii de emisii": ["Total"],
            "Statii de monitorizare de tip fond urban - Localitate":
                ["BT-1 - Municipiul Botosani"],
            "Ani": ["Anul 2024"],
            "Unitati de masura": ["Micrograme"],
            "Valoare": [26.23],
        }), m)
    col = "Statii de monitorizare de tip fond urban - Localitate"
    assert tidy[f"{col}_nivel"][0] == "necunoscut"
    assert tidy[f"{col}_siruta"][0] is pd.NA


def test_real_localities_still_detected(monkeypatch):
    """FOM104D are nomLoc pus, deci nimic nu se schimba pentru el."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    localitati = m.dimensions[1]
    assert territory.is_locality_dimension(localitati, m.details) is True
    assert m.levels == ["national", "judet", "localitate"]
    assert m.has_siruta is True


def test_localities_confirmed_by_siruta_prefixes(monkeypatch):
    """Fara nomLoc, dar cu prefixe SIRUTA pe optiuni: tot localitati."""
    fara_nomloc = dict(
        FOM104D,
        details=dict(FOM104D["details"], nomLoc=0, nomJud=0, matSiruta=0),
    )
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): fara_nomloc})
    m = t.matrix("FOM104D")
    localitati = m.dimensions[1]
    assert "localit" in localitati.label.lower()
    assert territory.is_locality_dimension(localitati, m.details) is True
    assert "localitate" in m.levels


def test_levels_and_siruta(monkeypatch):
    _fake_matrix(monkeypatch)
    m = t.matrix("FOM104D")
    assert m.levels == ["national", "judet", "localitate"]
    assert m.has_siruta is True


def test_option_level():
    assert territory.option_level("TOTAL") == "national"
    assert territory.option_level("MACROREGIUNEA UNU") == "macroregiune"
    assert territory.option_level("Regiunea NORD-VEST") == "regiune"
    assert territory.option_level("Bistrita-Nasaud") == "judet"
    assert territory.option_level("Municipiul Bucuresti") == "judet"
    # totalul national nu se scrie mereu 'TOTAL'
    assert territory.option_level("Nivel National") == "national"
    # grupari de judete si reziduuri nu sunt judete
    assert territory.option_level("Arges, Valcea") == "necunoscut"
    assert territory.option_level("Extra-regiuni") == "necunoscut"
    # ce nu e in nomenclatorul real nu mai cade automat pe judet
    assert territory.option_level("BT-1 - Municipiul Botosani") == "necunoscut"
    assert territory.option_level("Punct de trecere Nadlac") == "necunoscut"
    assert territory.option_level("") == "necunoscut"


def test_levels_hierarchical_from_details(monkeypatch):
    """SOM101B: nomJud si nomLoc sunt 0, dar matRegJ marcheaza dimensiunea."""
    _fake_api(monkeypatch)
    m = t.matrix("SOM101B")
    assert m.levels == ["national", "macroregiune", "regiune", "judet"]
    assert [d.role for d in m.dimensions] == ["teritoriu", "timp", "um"]


def test_levels_hierarchical_from_label(monkeypatch):
    """Acelasi rezultat cand details tace: detectia vine din label.

    FOM101A real are matRegJ = 2, deci l-ar prinde details. Il punem pe 0
    ca sa ramana doar label-ul care sa faca treaba.
    """
    fara_details = dict(FOM101A, details=dict(FOM101A["details"], matRegJ=0))
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM101A"): fara_details})
    m = t.matrix("FOM101A")
    assert m.levels == ["national", "macroregiune", "regiune", "judet"]
    assert m.dimensions[1].role == "teritoriu"


def test_levels_fom101a_as_published(monkeypatch):
    _fake_api(monkeypatch)
    assert t.matrix("FOM101A").levels == [
        "national", "macroregiune", "regiune", "judet"]


def test_siruta_from_label():
    assert territory.siruta_from_label("1017 MUNICIPIUL ALBA IULIA") == 1017
    assert territory.siruta_from_label("TOTAL") is None
    assert territory.siruta_from_label("") is None


def test_group_localities_by_county(monkeypatch):
    _fake_matrix(monkeypatch)
    m = t.matrix("FOM104D")
    groups = territory.group_localities_by_county(m.dimensions[1])
    # parentId al localitatii e nomItemId-ul judetului (Alba = 3064)
    assert [o.label for o in groups[3064]] == [
        "1017 MUNICIPIUL ALBA IULIA", "1026 ORAS ABRUD"]


def test_info_dict(monkeypatch):
    _fake_matrix(monkeypatch)
    d = t.info("FOM104D")
    assert d["code"] == "FOM104D"
    assert d["name"].startswith("Numarul mediu")
    assert d["last_updated"] == "20-11-2025"
    assert d["periodicity"] == ["Anuala"]
    assert d["levels"] == ["national", "judet", "localitate"]
    assert d["has_siruta"] is True
    assert d["dimensions"][1] == {
        "index": 1, "code": 2, "label": "Localitati", "role": "teritoriu",
        "n_options": 3}


def test_where_breadcrumb(monkeypatch):
    _fake_api(monkeypatch)
    crumbs = t.matrix("FOM104D")._breadcrumb()
    # 'home' cade (nu are cod), iar ancora din nume dispare cu tot cu textul ei
    assert list(crumbs) == ["A. STATISTICA SOCIALA", "FORTA DE MUNCA", "SALARIATI"]
    assert repr(crumbs) == "A. STATISTICA SOCIALA > FORTA DE MUNCA > SALARIATI"


def test_related_filters_siblings(monkeypatch):
    _fake_api(monkeypatch)
    rel = t.matrix("FOM104D").related()
    # exclude indicatorul curent si subnodurile care nu sunt matrice
    assert [m.code for m in rel] == ["FOM104A"]
    assert isinstance(rel, t.MatrixList)


def test_options_by_label_role_and_index(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    assert list(m.options("Judete")) == ["TOTAL", "Alba"]
    assert list(m.options("timp")) == ["Anul 1990"]
    assert list(m.options(3)) == ["Numar persoane"]
    # 'teritoriu' alege dimensiunea cea mai fina prezenta
    assert m.options("teritoriu")[1] == "1017 MUNICIPIUL ALBA IULIA"
    assert list(m.options("Judete", limit=1)) == ["TOTAL"]


def test_options_unknown_dimension(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    try:
        m.options("nu exista")
    except ValueError as e:
        assert "Disponibile" in str(e)
    else:
        raise AssertionError("trebuia ValueError")


def test_domains_top_level_only(monkeypatch):
    _fake_api(monkeypatch)
    doms = t.domains()
    assert [d.code for d in doms] == ["1", "2"]
    assert doms[1].name == "B. STATISTICA ECONOMICA"


def test_matrixlist_recent(monkeypatch):
    _fake_api(monkeypatch)
    lst = t.MatrixList([t.Matrix("SOM101B"), t.Matrix("FOM104D")])
    assert [m.code for m in lst.recent()] == ["FOM104D", "SOM101B"]


def test_matrixlist_shows_levels_when_all_known(monkeypatch):
    """Coloana apare doar daca toate elementele au nivelele deja, fara cost."""
    _fake_api(monkeypatch)
    lista = t.MatrixList([t.matrix("FOM104D")])   # metadate aduse
    html_out = lista._repr_html_()
    assert "<th>nivele</th>" in html_out
    assert "judet, localitate" in html_out
    assert "[national, judet, localitate]" in repr(lista)

    # din index, fara metadate: tot stiute
    din_index = t.MatrixList([t.Matrix("X", "x", cached_levels=["judet"])])
    assert "<th>nivele</th>" in din_index._repr_html_()
    # stiut ca nu are niciunul: coloana ramane, celula e goala
    gol = t.MatrixList([t.Matrix("Y", "y", cached_levels=[])])
    assert "<th>nivele</th>" in gol._repr_html_()


def test_matrixlist_hides_levels_when_any_unknown(monkeypatch):
    _fake_api(monkeypatch)
    # find simplu: doar cod si nume, nivelele nu se stiu
    necunoscut = t.MatrixList([t.Matrix("X", "x")])
    html_out = necunoscut._repr_html_()
    assert "<tr><th>cod</th><th>nume</th></tr>" in html_out
    assert "<th>nivele</th>" not in html_out

    # lista mixta: un singur element necunoscut ascunde coloana
    mixta = t.MatrixList([t.matrix("FOM104D"), t.Matrix("X", "x")])
    assert "<th>nivele</th>" not in mixta._repr_html_()

    # domeniile nu au nivele deloc
    from pytempo.models import Node
    domenii = t.MatrixList([Node(code="1", name="A. STATISTICA SOCIALA")])
    assert "<th>nivele</th>" not in domenii._repr_html_()


def test_level_literal_matches_level_order():
    """Literal-ul si tuplul trebuie sa ramana sincronizate."""
    from typing import get_args
    assert get_args(territory.Level) == territory._LEVEL_ORDER


def test_unknown_level_suggests_closest():
    from pytempo import catalog as c
    try:
        c.search(level="judete")
    except ValueError as e:
        mesaj = str(e)
    else:
        raise AssertionError("trebuia ValueError")
    assert "nivel necunoscut 'judete'" in mesaj
    assert "national, macroregiune, regiune, judet, localitate" in mesaj
    assert "Poate ai vrut 'judet'?" in mesaj


def test_unknown_level_without_suggestion():
    try:
        t.search(level="zzzzz")
    except ValueError as e:
        mesaj = str(e)
    else:
        raise AssertionError("trebuia ValueError")
    assert "nivel necunoscut 'zzzzz'" in mesaj
    assert "Posibile:" in mesaj
    assert "Poate ai vrut" not in mesaj


def test_get_and_search_share_error_format(monkeypatch):
    _fake_api(monkeypatch)
    try:
        t.matrix("FOM101A").get(level="judete")
    except ValueError as e:
        din_get = str(e)
    else:
        raise AssertionError("trebuia ValueError din get")
    try:
        t.search(level="judete")
    except ValueError as e:
        din_search = str(e)
    else:
        raise AssertionError("trebuia ValueError din search")

    for mesaj in (din_get, din_search):
        assert mesaj.startswith("nivel necunoscut 'judete'")
        assert "Posibile:" in mesaj
        assert "Poate ai vrut 'judet'?" in mesaj
    # get spune si la ce indicator, si listeaza nivelele acelui indicator
    assert "la FOM101A" in din_get
    assert "localitate" not in din_get      # FOM101A nu are localitate
    assert "localitate" in din_search       # search listeaza toate nivelele


def test_filters_levels_match_literal(monkeypatch, tmp_path, capsys):
    from typing import get_args
    _index_pe_disc(monkeypatch, tmp_path)
    _fake_api(monkeypatch)
    t.filters()
    iesire = capsys.readouterr().out
    for nivel in get_args(territory.Level):
        assert nivel in iesire


def test_matrix_card_html_has_levels(monkeypatch):
    """Pe cardul unui singur indicator nivelele chiar sunt disponibile."""
    _fake_api(monkeypatch)
    html_out = t.matrix("FOM104D")._repr_html_()
    assert "judet, localitate" in html_out
    assert "Localitati" in html_out


# CSV ca de la pivot: spatiu dupa fiecare virgula, zecimala punct, fara
# ghilimele, un intreg fara parte zecimala (13544). Rar: combinatia
# (Feminin, Ilfov, Anul 1990) lipseste ca rand intreg, nu ca valoare goala.
CSV_FOM101A = (
    "Sexe, Macroregiuni  regiuni de dezvoltare si judete, Ani, UM: Mii persoane, Valoare\n"
    "Total, TOTAL, Anul 1990, Mii persoane, 13216.9\n"
    "Total, TOTAL, Anul 2003, Mii persoane, 13544\n"
    "Total, Ilfov, Anul 1990, Mii persoane, 102.4\n"
    "Feminin, TOTAL, Anul 1990, Mii persoane, 6512.3\n"
    "Feminin, Vrancea, Anul 2024, Mii persoane, 96.1\n"
)


def test_parse_pivot_csv(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM101A")
    df = parse.pivot_csv_to_dataframe(CSV_FOM101A, m)

    assert df.shape == (5, 5)
    assert df.shape[1] == len(m.dimensions) + 1
    # numele vin din dimensiuni, nu din antetul curatat de INS
    assert df.columns.tolist() == [
        "Sexe", "Macroregiuni, regiuni de dezvoltare si judete", "Ani",
        "UM: Mii persoane", "Valoare"]
    assert str(df["Valoare"].dtype) == "float64"
    assert df["Valoare"].tolist() == [13216.9, 13544.0, 102.4, 6512.3, 96.1]
    # pandas 2 da 'object' pentru text, pandas 3 da 'str'; conteaza doar ca
    # nu e numeric
    assert str(df["Sexe"].dtype) in ("object", "str")
    assert df["Sexe"].tolist()[0] == "Total"


def test_parse_sparse_rows_are_absent_not_nan(monkeypatch):
    """Combinatia lipsa nu produce NaN, pur si simplu nu exista ca rand."""
    _fake_api(monkeypatch)
    df = parse.pivot_csv_to_dataframe(CSV_FOM101A, t.matrix("FOM101A"))
    assert df["Valoare"].isna().sum() == 0
    lipsa = df[(df["Sexe"] == "Feminin")
               & (df["Macroregiuni, regiuni de dezvoltare si judete"] == "Ilfov")]
    assert len(lipsa) == 0


def test_parse_empty_csv_is_not_an_error(monkeypatch):
    """Un raspuns fara randuri e legitim, nu o mapare gresita de coloane."""
    _fake_api(monkeypatch)
    doar_antet = ("Sexe, Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                  "UM: Mii persoane, Valoare\n")
    df = parse.pivot_csv_to_dataframe(doar_antet, t.matrix("FOM101A"))
    assert df.empty
    assert df.shape[1] == 5
    assert str(df["Valoare"].dtype) == "float64"


def test_parse_wrong_column_count(monkeypatch):
    _fake_api(monkeypatch)
    stricat = "A, B, Valoare\nx, y, 1.0\n"
    try:
        parse.pivot_csv_to_dataframe(stricat, t.matrix("FOM101A"))
    except ValueError as e:
        assert "3 coloane" in str(e) and "asteptate 5" in str(e)
    else:
        raise AssertionError("trebuia ValueError la numar gresit de coloane")


def test_parse_value_column_not_numeric(monkeypatch):
    _fake_api(monkeypatch)
    text = (
        "Sexe, Terr, Ani, UM, Valoare\n"
        "Total, TOTAL, Anul 1990, Mii persoane, nu e numar\n"
    )
    try:
        parse.pivot_csv_to_dataframe(text, t.matrix("FOM101A"))
    except ValueError as e:
        assert "nu e numerica" in str(e)
    else:
        raise AssertionError("trebuia ValueError la Valoare ne-numerica")


def test_build_encquery():
    assert chunking.build_encquery([[105, 106], [112], [4247, 4266]]) == \
        "105,106:112:4247,4266"
    assert chunking.build_encquery([[1]]) == "1"


def test_get_builds_payload_and_parses(monkeypatch):
    """get() ia toate optiunile, in ordinea din dimensionsMap."""
    _fake_api(monkeypatch)
    trimis = {}

    def fake_post(payload, **kw):
        trimis.update(payload)
        return CSV_FOM101A

    monkeypatch.setattr(client, "post_pivot", fake_post)
    df = t.matrix("FOM101A").get(level=None, raw=True,
                                 progress=False)

    assert trimis["matCode"] == "FOM101A"
    assert trimis["language"] == "ro"
    assert trimis["matMaxDim"] == 4
    assert trimis["matUMSpec"] == 0
    # patru dimensiuni, deci trei separatori de dimensiune
    assert trimis["encQuery"].count(":") == 3
    assert trimis["encQuery"].split(":")[1] == "1,2,3,4,5"
    assert df.shape == (5, 5)


# SOM101B din fixture are 3 dimensiuni, deci 4 coloane
CSV_SOM101B = (
    "Macroregiuni  regiuni de dezvoltare si judete, Ani, UM: Numar persoane, Valoare\n"
    "Bihor, Anul 2020, Numar persoane, 12.5\n"
    "Cluj, Anul 2020, Numar persoane, 18.0\n"
)


def _capture_post(monkeypatch, csv_text=CSV_SOM101B):
    """Prinde payload-ul trimis la pivot, fara retea."""
    trimis = {}

    def fake_post(payload, **kw):
        trimis.update(payload)
        return csv_text

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return trimis


def _dim_codes(encquery, index):
    return [int(c) for c in encquery.split(":")[index].split(",")]


def test_get_level_judet_filters_options(monkeypatch):
    """Doar judetele, fara TOTAL, MACROREGIUNEA sau Regiunea."""
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    t.matrix("SOM101B").get(level="judet")
    # in fixture teritoriul e prima dimensiune, deci primul bloc din encQuery
    assert _dim_codes(trimis["encQuery"], 0) == [4, 5]  # Bihor, Cluj


def test_get_level_macroregiune(monkeypatch):
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    t.matrix("SOM101B").get(level="macroregiune")
    assert _dim_codes(trimis["encQuery"], 0) == [2]  # MACROREGIUNEA UNU


def test_get_levels_list_accumulates(monkeypatch):
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    t.matrix("SOM101B").get(levels=["national", "regiune"])
    assert _dim_codes(trimis["encQuery"], 0) == [1, 3]  # TOTAL, Regiunea


def test_get_other_dimensions_stay_complete(monkeypatch):
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    t.matrix("SOM101B").get(level="judet")
    parts = trimis["encQuery"].split(":")
    assert parts[1] == "20"  # Ani, intreaga
    assert parts[2] == "30"  # UM, intreaga


def test_get_unknown_level(monkeypatch):
    _fake_api(monkeypatch)
    _capture_post(monkeypatch)
    try:
        t.matrix("SOM101B").get(level="localitate")
    except ValueError as e:
        assert "nivel necunoscut 'localitate' la SOM101B" in str(e)
        assert "Posibile: national, macroregiune, regiune, judet" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru nivel inexistent")


def test_get_level_two_territorial_dimensions(monkeypatch):
    """FOM104D are judet si localitate separate; filtrul vine la 3c."""
    _fake_api(monkeypatch)
    _capture_post(monkeypatch)
    try:
        t.matrix("FOM104D").get(level="judet")
    except NotImplementedError as e:
        assert "iteratia 3c" in str(e)
    else:
        raise AssertionError("trebuia NotImplementedError, nu tot setul tacut")


def test_big_matrix_without_localities_is_split(monkeypatch):
    """Fara localitati dupa care sa se sparga, se sparge pe cea mai mare
    dimensiune. Nimic nu mai esueaza cu eroare de marime."""
    mare = dict(SOM101B, dimensionsMap=[
        dict(SOM101B["dimensionsMap"][0]),
        {"dimCode": 4, "label": "Ani", "options": [
            {"label": f"Anul {an}", "nomItemId": 1000 + an, "offset": 1,
             "parentId": None} for an in range(1990, 2025)]},
        {"dimCode": 9, "label": "Categorii", "options": [
            {"label": f"C{i}", "nomItemId": 2000 + i, "offset": 1,
             "parentId": None} for i in range(900)]},
    ])
    _fake_api(monkeypatch, extra={endpoints.matrix("SOM101B"): mare})
    m = t.matrix("SOM101B")
    assert 5 * 35 * 900 > MAX_CELLS

    selectie = [[o.nom_item_id for o in d.options] for d in m.dimensions]
    planuri = chunking.plan_requests(m, selectie)
    assert len(planuri) > 1
    # fiecare cerere incape sub prag
    for p in planuri:
        bucati = [bloc.split(",") for bloc in p["encQuery"].split(":")]
        produs = 1
        for b in bucati:
            produs *= len(b)
        assert produs <= MAX_CELLS
    # nicio optiune pierduta pe dimensiunea sparta
    toate = [c for p in planuri for c in p["encQuery"].split(":")[2].split(",")]
    assert len(set(toate)) == 900

    # cu filtru pe nivel incape intr-o singura cerere
    trimis = _capture_post(monkeypatch)
    m.get(level="judet", progress=False)
    assert _dim_codes(trimis["encQuery"], 0) == [4, 5]


def test_matrix_refresh_bypasses_cache(monkeypatch):
    _fake_index(monkeypatch)
    vazut = {}

    def fake_get_json(url, **kw):
        vazut["use_cache"] = kw.get("use_cache")
        return FOM101A

    monkeypatch.setattr(client, "get_json", fake_get_json)
    t.matrix("FOM101A", refresh=True)
    assert vazut["use_cache"] is False
    t.matrix("FOM101A")
    assert vazut["use_cache"] is True


def test_parse_territory_localities():
    assert territory.parse_territory("1017 MUNICIPIUL ALBA IULIA") == \
        (1017, "localitate", "municipiu", "ALBA IULIA")
    assert territory.parse_territory("1151 ORAS ABRUD") == \
        (1151, "localitate", "oras", "ABRUD")
    # comunele vin fara prefix de tip
    assert territory.parse_territory("2130 ALBAC") == \
        (2130, "localitate", "comuna", "ALBAC")
    assert territory.parse_territory("179132 SECTORUL 1") == \
        (179132, "localitate", "sector", "1")


def test_parse_territory_aggregates():
    assert territory.parse_territory("TOTAL") == (None, "national", None, "TOTAL")
    assert territory.parse_territory("MACROREGIUNEA UNU") == \
        (None, "macroregiune", None, "MACROREGIUNEA UNU")
    assert territory.parse_territory("Regiunea NORD-VEST") == \
        (None, "regiune", None, "Regiunea NORD-VEST")
    assert territory.parse_territory("Cluj") == (None, "judet", None, "Cluj")


def test_standardize_adds_columns_without_losing_anything(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    terr = m.dimensions[1].label.strip()   # 'Localitati'
    an = m.dimensions[2].label.strip()     # 'Ani'
    df = pd.DataFrame({
        m.dimensions[0].label.strip(): ["TOTAL"] * 7,
        terr: ["1017 MUNICIPIUL ALBA IULIA", "1151 ORAS ABRUD", "2130 ALBAC",
               "TOTAL", "MACROREGIUNEA UNU", "Regiunea NORD-VEST", "Cluj"],
        an: ["Anul 2024"] * 6 + ["fara an"],
        m.dimensions[3].label.strip(): ["Numar persoane"] * 7,
        "Valoare": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
    })
    out = parse.standardize(df, m)

    # nimic nu se pierde: aceleasi randuri, aceeasi ordine, coloanele originale
    assert len(out) == len(df)
    assert list(out[terr]) == list(df[terr])
    assert out[terr][0] == "1017 MUNICIPIUL ALBA IULIA"
    assert list(out["Valoare"]) == list(df["Valoare"])

    assert out[f"{terr}_siruta"].tolist()[:3] == [1017, 1151, 2130]
    assert out[f"{terr}_siruta"][3] is pd.NA      # TOTAL nu are SIRUTA
    assert out[f"{terr}_siruta"][6] is pd.NA      # nici judetul Cluj
    assert list(out[f"{terr}_nivel"]) == [
        "localitate", "localitate", "localitate",
        "national", "macroregiune", "regiune", "judet"]
    assert list(out[f"{terr}_tip"])[:3] == ["municipiu", "oras", "comuna"]
    assert out[f"{terr}_tip"][3] is pd.NA
    assert list(out[f"{terr}_nume"])[:3] == ["ALBA IULIA", "ABRUD", "ALBAC"]

    assert out[f"{an}_an"][0] == 2024
    assert out[f"{an}_an"][6] is pd.NA


def test_get_tidy(monkeypatch):
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    brut = t.matrix("SOM101B").get(level="judet", raw=True,
                                   progress=False)
    tidy = t.matrix("SOM101B").get(level="judet", tidy=True,
                                   progress=False)
    assert trimis["matCode"] == "SOM101B"
    # tidy adauga coloane, nu randuri
    assert len(tidy) == len(brut)
    assert tidy.shape[1] > brut.shape[1]
    terr = "Macroregiuni, regiuni de dezvoltare si judete"
    assert f"{terr}_nivel" in tidy.columns
    assert "Ani_an" in tidy.columns
    assert list(tidy[f"{terr}_nivel"]) == ["judet", "judet"]
    assert tidy["Ani_an"].tolist() == [2020, 2020]


# FOM104D in mic: doua judete, cu localitatile lor legate prin parentId
FOM104D_MIC = dict(
    FOM104D,
    dimensionsMap=[
        {"dimCode": 1, "label": "Judete", "options": [
            {"label": "TOTAL", "nomItemId": 112, "offset": 1, "parentId": None},
            {"label": "Alba", "nomItemId": 3064, "offset": 2, "parentId": None},
            {"label": "Arad", "nomItemId": 3065, "offset": 3, "parentId": None},
        ]},
        {"dimCode": 2, "label": "Localitati", "options": [
            {"label": "TOTAL", "nomItemId": 112, "offset": 0, "parentId": 112},
            {"label": "1017 MUNICIPIUL ALBA IULIA", "nomItemId": 113,
             "offset": 2, "parentId": 3064},
            {"label": "1151 ORAS ABRUD", "nomItemId": 114, "offset": 3,
             "parentId": 3064},
            {"label": "2130 ALBAC", "nomItemId": 115, "offset": 4,
             "parentId": 3064},
            {"label": "3000 MUNICIPIUL ARAD", "nomItemId": 116, "offset": 5,
             "parentId": 3065},
        ]},
        {"dimCode": 3, "label": "Ani", "options": [
            {"label": "Anul 2023", "nomItemId": 4247, "offset": 1,
             "parentId": None},
            {"label": "Anul 2024", "nomItemId": 4266, "offset": 2,
             "parentId": None},
        ]},
        {"dimCode": 4, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 9685, "offset": 1,
             "parentId": None}]},
    ],
)

CSV_FOM104D = (
    "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
    "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, Numar persoane, 31.5\n"
    "Alba, 2130 ALBAC, Anul 2024, Numar persoane, 1.2\n"
)


def _plan_for(m, max_cells):
    selection = [[o.nom_item_id for o in d.options] for d in m.dimensions]
    return chunking.plan_requests(m, selection, max_cells=max_cells)


def test_plan_requests_single_payload_when_small(monkeypatch):
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    m = t.matrix("FOM104D")
    planuri = _plan_for(m, max_cells=MAX_CELLS)
    assert len(planuri) == 1
    assert planuri[0]["matCode"] == "FOM104D"


def test_plan_requests_one_payload_per_county(monkeypatch):
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    m = t.matrix("FOM104D")
    # 3 judete x 5 localitati x 2 ani = 30, deci pragul 10 forteaza spargerea
    planuri = _plan_for(m, max_cells=10)
    assert len(planuri) == 3  # TOTAL, Alba, Arad

    pe_judet = {}
    for p in planuri:
        blocuri = p["encQuery"].split(":")
        pe_judet[blocuri[0]] = blocuri[1]
    # fiecare cerere are un singur judet si doar localitatile lui
    assert pe_judet["112"] == "112"
    assert pe_judet["3064"] == "113,114,115"
    assert pe_judet["3065"] == "116"
    # celelalte dimensiuni raman intregi
    assert all(p["encQuery"].split(":")[2] == "4247,4266" for p in planuri)


def test_plan_requests_splits_a_big_county(monkeypatch):
    """Un judet care nu incape se sparge mai departe, sub prag."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    m = t.matrix("FOM104D")
    # cu prag 2, judetul Alba (3 localitati x 2 ani = 6) nu incape intreg
    alba = [p for p in _plan_for(m, max_cells=2)
            if p["encQuery"].startswith("3064:")]
    assert [p["encQuery"].split(":")[1] for p in alba] == ["113", "114", "115"]
    # bucata de o localitate x 2 ani chiar incape sub prag
    assert all(p["encQuery"].split(":")[2] == "4247,4266" for p in alba)


def test_split_selection_fits_every_chunk():
    """Bucatile ies dimensionate dupa cat loc lasa celelalte dimensiuni."""
    selectie = [list(range(10)), list(range(4)), [99]]   # 40 de celule
    bucati = chunking.split_selection(selectie, max_cells=8)
    assert all(chunking.cells(b) <= 8 for b in bucati)
    # nimic pierdut, nimic repetat: bucatile insumeaza exact selectia
    assert sum(chunking.cells(b) for b in bucati) == 40
    acoperite = {(a, b_, c) for b in bucati
                 for a in b[0] for b_ in b[1] for c in b[2]}
    assert len(acoperite) == 40


def test_split_selection_recurses_when_one_option_is_still_too_big():
    """Daca nici o singura optiune nu incape, coboara pe alta dimensiune."""
    selectie = [list(range(5)), list(range(20))]        # 100 de celule
    bucati = chunking.split_selection(selectie, max_cells=6)
    assert all(chunking.cells(b) <= 6 for b in bucati)
    assert sum(chunking.cells(b) for b in bucati) == 100
    # a trebuit sa taie si a doua dimensiune, nu doar prima
    assert any(len(b[1]) < 20 for b in bucati)


def test_get_concatenates_chunked_results(monkeypatch):
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return CSV_FOM104D

    monkeypatch.setattr(client, "post_pivot", fake_post)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    df = t.matrix("FOM104D").get()
    assert len(cereri) == 3
    # doua randuri per cerere, nimic pierdut la concatenare
    assert len(df) == 6
    assert list(df.index) == list(range(6))


def test_get_chunked_tidy_keeps_siruta(monkeypatch):
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    monkeypatch.setattr(client, "post_pivot", lambda payload, **kw: CSV_FOM104D)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    df = t.matrix("FOM104D").get(tidy=True)
    assert df["Localitati_siruta"].tolist()[:2] == [1017, 2130]
    assert df["Localitati_tip"].tolist()[:2] == ["municipiu", "comuna"]
    assert df["Localitati"][0] == "1017 MUNICIPIUL ALBA IULIA"
    assert df["Ani_an"].tolist()[:2] == [2024, 2024]


# acelasi FOM104D mic, dar dimensiunea de judete are un label neobisnuit.
# Rolul ii vine din details (nomJud = 1), nu din label, iar _county_index
# trebuie sa o gaseasca prin potrivirea parentId-urilor.
FOM104D_LABEL_CIUDAT = dict(
    FOM104D_MIC,
    dimensionsMap=[
        dict(FOM104D_MIC["dimensionsMap"][0], label="Unitati de nivel superior"),
        FOM104D_MIC["dimensionsMap"][1],
        FOM104D_MIC["dimensionsMap"][2],
        FOM104D_MIC["dimensionsMap"][3],
    ],
)


def test_county_index_found_by_parent_ids_not_by_label(monkeypatch):
    _fake_api(monkeypatch,
              extra={endpoints.matrix("FOM104D"): FOM104D_LABEL_CIUDAT})
    m = t.matrix("FOM104D")
    assert m.dimensions[0].label == "Unitati de nivel superior"
    assert m.dimensions[0].role == "teritoriu"   # din details, nomJud = 1

    planuri = _plan_for(m, max_cells=10)
    pe_judet = {p["encQuery"].split(":")[0]: p["encQuery"].split(":")[1]
                for p in planuri}
    assert pe_judet["3064"] == "113,114,115"
    assert pe_judet["3065"] == "116"


def test_county_index_absent_when_no_second_territorial_dimension(monkeypatch):
    """Fara dimensiune de judete, spargerea se face doar pe localitati."""
    fara_judete = dict(
        FOM104D_MIC,
        details=dict(FOM104D_MIC["details"], nomJud=0),
        dimensionsMap=FOM104D_MIC["dimensionsMap"][1:],
    )
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): fara_judete})
    m = t.matrix("FOM104D")
    planuri = _plan_for(m, max_cells=4)
    # cate o cerere per grup de parentId; grupul care nu incape se mai sparge
    blocuri = sorted(p["encQuery"].split(":")[0] for p in planuri)
    assert blocuri == ["112", "113,114", "115", "116"]


def test_chunked_requests_keep_row_order(monkeypatch):
    """Concatenarea pastreaza toate randurile si ordinea cererilor."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    def fake_post(payload, **kw):
        judet = payload["encQuery"].split(":")[0]
        return (
            "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
            f"J{judet}, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, Numar persoane, 1\n"
            f"J{judet}, 2130 ALBAC, Anul 2024, Numar persoane, 2\n"
        )

    monkeypatch.setattr(client, "post_pivot", fake_post)
    df = t.matrix("FOM104D").get()
    assert len(df) == 6
    assert list(df.index) == list(range(6))
    # ordinea judetelor din plan se pastreaza in rezultat
    assert df["Judete"].tolist() == [
        "J112", "J112", "J3064", "J3064", "J3065", "J3065"]


def test_big_county_produces_several_requests(monkeypatch):
    """Un judet ale carui localitati nu incap singure declanseaza split_options."""
    multe = [{"label": f"{5000 + i} COMUNA{i}", "nomItemId": 200 + i,
              "offset": i, "parentId": 3064} for i in range(250)]
    mare = dict(FOM104D_MIC, dimensionsMap=[
        FOM104D_MIC["dimensionsMap"][0],
        dict(FOM104D_MIC["dimensionsMap"][1], options=multe),
        FOM104D_MIC["dimensionsMap"][2],
        FOM104D_MIC["dimensionsMap"][3],
    ])
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): mare})
    m = t.matrix("FOM104D")
    # un singur judet, 250 localitati x 2 ani = 500 celule, peste pragul 100
    planuri = _plan_for(m, max_cells=100)
    # 250 localitati x 2 ani: bucata se dimensioneaza dupa anii ramasi
    bucati = [p["encQuery"].split(":")[1].split(",") for p in planuri]
    assert [len(b) for b in bucati] == [50, 50, 50, 50, 50]
    assert all(len(b) * 2 <= 100 for b in bucati)
    # nicio localitate pierduta, niciuna repetata
    toate = [c for b in bucati for c in b]
    assert len(toate) == len(set(toate)) == 250


def test_level_filter_runs_before_planning(monkeypatch):
    """level reduce selectia inainte de planificare, deci nu se mai sparge."""
    _fake_api(monkeypatch)
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return CSV_SOM101B

    monkeypatch.setattr(client, "post_pivot", fake_post)
    monkeypatch.setattr(chunking, "MAX_CELLS", 3)
    m = t.matrix("SOM101B")

    # fara filtru, selectia depaseste pragul mic si se sparge in mai multe
    m.get(level=None, progress=False)
    assert len(cereri) > 1

    # cu filtru pe nivel incape intr-o singura cerere
    cereri.clear()
    m.get(level="judet", progress=False)
    assert len(cereri) == 1
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"


def test_parse_territory_prefix_needs_a_space():
    """Potrivirea e pe prefix plus spatiu, nu pe substring.

    'ORASENI DEAL' e o comuna al carei nume incepe cu literele lui ORAS.
    """
    assert territory.parse_territory("5000 ORASENI DEAL") == \
        (5000, "localitate", "comuna", "ORASENI DEAL")
    assert territory.parse_territory("5001 COMUNESTI") == \
        (5001, "localitate", "comuna", "COMUNESTI")
    # prefixul lung castiga fata de cel scurt
    assert territory.parse_territory("5002 ORASUL NOU")[2] == "oras"
    assert territory.parse_territory("5002 ORASUL NOU")[3] == "NOU"
    assert territory.parse_territory("179132 SECTORUL 3") == \
        (179132, "localitate", "sector", "3")
    assert territory.parse_territory("179133 SECTOR 4")[2] == "sector"


def test_parse_territory_empty_and_blank():
    """Nu crapa pe gol; fara cifre in fata nu exista SIRUTA."""
    for gol in ("", "   ", None):
        siruta, nivel, tip, nume = territory.parse_territory(gol)
        assert siruta is None and tip is None
        assert nume == ""
        assert nivel == "necunoscut"   # gol nu e nici judet, nici altceva


def test_standardize_malformed_year_gives_na(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM101A")
    an = m.dimensions[2].label.strip()
    df = pd.DataFrame({
        m.dimensions[0].label.strip(): ["Total"] * 3,
        m.dimensions[1].label.strip(): ["Cluj"] * 3,
        an: ["Anul 2024", "Anul necunoscut", ""],
        m.dimensions[3].label.strip(): ["Mii persoane"] * 3,
        "Valoare": [1.0, 2.0, 3.0],
    })
    out = parse.standardize(df, m)
    assert out[f"{an}_an"][0] == 2024
    assert out[f"{an}_an"][1] is pd.NA
    assert out[f"{an}_an"][2] is pd.NA


def test_standardize_empty_frame(monkeypatch):
    """Un rezultat fara randuri nu trebuie sa crape standardizarea."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM101A")
    gol = pd.DataFrame({d.label.strip(): [] for d in m.dimensions} |
                       {"Valoare": []})
    out = parse.standardize(gol, m)
    assert len(out) == 0
    assert f"{m.dimensions[1].label.strip()}_siruta" in out.columns


def test_public_api_names_all_resolve():
    """Niciun export mort in __all__."""
    for name in t.__all__:
        assert hasattr(t, name), f"{name} lipseste din pachet"
    for name in ("load_index", "name_dict", "search", "find", "domains",
                 "overview", "matrix", "info", "get", "help"):
        assert callable(getattr(t, name)), f"{name} nu e apelabil"
    assert isinstance(t.__version__, str)


def test_help_runs(monkeypatch, capsys):
    t.help()
    iesire = capsys.readouterr().out
    assert "find" in iesire and "get" in iesire

    _fake_api(monkeypatch)
    t.matrix("FOM104D").help()
    iesire = capsys.readouterr().out
    assert "FOM104D" in iesire and ".get(" in iesire


def test_show_runs(monkeypatch, capsys):
    _fake_api(monkeypatch)
    t.matrix("FOM104D").show()
    iesire = capsys.readouterr().out
    assert "FOM104D" in iesire and "dimensiuni" in iesire


# FOM104F: matCaen1 si matCaen2 sunt 0, dar dimensiunea 1 e clar CAEN.
# Rolul trebuie prins din label, exact ca la teritoriu.
FOM104F = {
    "matrixName": "Numarul mediu al salariatilor pe activitati ale economiei nationale",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "20-11-2025",
    "periodicitati": ["Anuala"], "surseDeDate": [],
    "ancestors": [{"name": "A. STATISTICA SOCIALA", "code": "1"}],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 4, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 3, "matMaxDim": 5,
                "matUMSpec": 0},
    "dimensionsMap": [
        {"dimCode": 1, "label": "CAEN Rev.2  (activitati ale economiei nationale)",
         "options": [{"label": "TOTAL", "nomItemId": 50, "offset": 1,
                      "parentId": None}]},
        {"dimCode": 2, "label": "Sexe", "options": [
            {"label": "Total", "nomItemId": 51, "offset": 1, "parentId": None}]},
        {"dimCode": 3, "label": "Macroregiuni, regiuni de dezvoltare si judete",
         "options": _IERARHIC},
        {"dimCode": 4, "label": "Ani", "options": [
            {"label": "Anul 2024", "nomItemId": 52, "offset": 1,
             "parentId": None}]},
        {"dimCode": 5, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 53, "offset": 1,
             "parentId": None}]},
    ],
}


def test_caen_role_from_label(monkeypatch):
    """Fara flag in details, CAEN-ul se prinde din label."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): FOM104F})
    m = t.matrix("FOM104F")
    assert [d.role for d in m.dimensions] == [
        "caen", "alt", "teritoriu", "timp", "um"]


def test_caen_role_from_details(monkeypatch):
    """Cu flagul pus, tot 'caen', chiar daca labelul nu spune nimic."""
    cu_flag = dict(
        FOM104F,
        details=dict(FOM104F["details"], matCaen1=1),
        dimensionsMap=[dict(FOM104F["dimensionsMap"][0], label="Activitati")]
        + FOM104F["dimensionsMap"][1:],
    )
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): cu_flag})
    assert t.matrix("FOM104F").dimensions[0].role == "caen"


def test_non_caen_dimension_stays_alt(monkeypatch):
    """Fara 'caen' in label si fara flag, ramane 'alt'."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): FOM104F})
    m = t.matrix("FOM104F")
    assert m.dimensions[1].label == "Sexe"
    assert m.dimensions[1].role == "alt"


def _index_and_meta(monkeypatch, meta_by_code):
    """Index injectat plus metadate per cod; numara apelurile de metadate."""
    apeluri = []
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Numar mediu salariati {c}"}
                         for c in meta_by_code])

    def fake_get_json(url, **kw):
        for cod, date in meta_by_code.items():
            if url == endpoints.matrix(cod):
                apeluri.append(cod)
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    return apeluri


def _cache_in(monkeypatch, tmp_path):
    """Muta cache-ul si indexul de nivele intr-un director temporar.

    Ascunde si registrul din pachet: el are prioritate la filtre, deci fara
    asta testele despre indexul vechi ar citi de fapt registrul real.
    """
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path / "data" / "raw")
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH",
                        tmp_path / "fara_registru.json")
    return tmp_path / "data" / catalog.INDEX_FILE


TOATE_META = {"FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A}


def test_find_without_level_fetches_no_metadata(monkeypatch):
    apeluri = _index_and_meta(monkeypatch, TOATE_META)
    rez = t.find("salariati")
    assert len(rez) == 3
    assert apeluri == []          # raspuns doar din indexul de nume


def test_find_returns_everything_without_limit(monkeypatch):
    _index_and_meta(monkeypatch, TOATE_META)
    assert len(t.find("salariati")) == 3
    assert len(t.find("salariati", limit=2)) == 2
    assert len(t.search("salariati")) == 3


def test_build_index_writes_file_and_skips_errors(monkeypatch, tmp_path,
                                                  capsys):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)

    # SOM101B da eroare la metadate: e sarit, nu opreste constructia
    adevarat = t.matrix

    def matrix_cu_eroare(cod, **kw):
        if cod == "SOM101B":
            raise ValueError("indisponibil")
        return adevarat(cod, **kw)

    monkeypatch.setattr(catalog, "matrix", matrix_cu_eroare)

    idx = t.build_index(confirm=False, progress=True)
    assert cale.exists()
    assert set(idx) == {"FOM104D", "FOM101A"}
    assert idx["FOM104D"]["levels"] == ["national", "judet", "localitate"]
    iesire = capsys.readouterr().out
    assert "construiesc indexul: 3/3" in iesire
    assert "sarite" in iesire

    pe_disc = json.loads(cale.read_text(encoding="utf-8"))
    assert pe_disc == idx


def test_build_index_respects_refresh(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text('{"VECHI": {"levels": ["judet"]}}', encoding="utf-8")
    apeluri = _index_and_meta(monkeypatch, TOATE_META)

    # fisierul exista, deci nu reconstruieste si nu atinge reteaua
    idx = t.build_index(confirm=False, progress=False)
    assert set(idx) == {"VECHI"}
    assert apeluri == []

    idx = t.build_index(confirm=False, progress=False, refresh=True)
    assert set(idx) == set(TOATE_META)
    assert apeluri


def test_build_index_asks_before_building(monkeypatch, tmp_path, capsys):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert t.build_index() is None
    assert not cale.exists()
    assert "nu construiesc" in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda _: "da")
    idx = t.build_index(progress=False)
    assert set(idx) == set(TOATE_META)
    assert cale.exists()


def test_build_index_refusal_without_stdin(monkeypatch, tmp_path):
    """Fara stdin, intrebarea nu poate primi raspuns: se considera nu."""
    _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)

    def fara_stdin(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", fara_stdin)
    assert t.build_index() is None


def test_search_with_level_uses_index_without_network(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text(json.dumps({
        "FOM104D": {"levels": ["national", "judet", "localitate"]},
        "SOM101B": {"levels": ["national", "judet"]},
        "FOM101A": {"levels": ["national", "judet"]},
    }), encoding="utf-8")
    apeluri = _index_and_meta(monkeypatch, TOATE_META)

    rez = t.search("salariati", level="localitate")
    assert [m.code for m in rez] == ["FOM104D"]
    assert apeluri == []          # indexul raspunde, fara retea

    rez = t.search("salariati", level="judet")
    assert sorted(m.code for m in rez) == ["FOM101A", "FOM104D", "SOM101B"]
    assert apeluri == []


def test_search_with_level_builds_index_after_confirmation(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)
    monkeypatch.setattr("builtins.input", lambda _: "d")

    rez = t.search("salariati", level="localitate")
    assert [m.code for m in rez] == ["FOM104D"]
    assert cale.exists()


def test_search_with_level_refused_returns_empty(monkeypatch, tmp_path, capsys):
    _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    rez = t.search("salariati", level="localitate")
    assert list(rez) == []
    assert "Fara indexul de metadate nu pot filtra" in capsys.readouterr().out


def test_search_unknown_level(monkeypatch):
    _fake_api(monkeypatch)
    try:
        t.search("salariati", level="comuna")
    except ValueError as e:
        assert "nivel necunoscut 'comuna'" in str(e) and "Posibile:" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru nivel necunoscut")


# fixture cu texte lungi, ca la INS: definitia are mai multe paragrafe si o
# fraza distinctiva la coada, ca sa se vada daca a fost taiata
DEFINITIE_LUNGA = (
    "Numarul mediu al salariatilor cuprinde persoanele angajate cu contract "
    "de munca pe durata determinata sau nedeterminata.\n"
    + "Paragraf intermediar de umplutura. " * 40
    + "\nIncepand cu anul 2003, din efectivele zilnice luate in calculul "
      "numarului mediu au fost exclusi salariatii al caror contract de munca "
      "a fost suspendat, conform prevederilor legale in vigoare."
)

FOM104D_CU_TEXT = dict(
    FOM104D,
    definitie=DEFINITIE_LUNGA,
    metodologie="Repartizarea salariatilor pe judete s-a realizat in functie "
                "de localitatea in care acestia isi desfasoara activitatea.",
    observatii="Datele la nivel de localitati au fost recalculate.\n"
               "Datele pentru anul 1990 sunt disponibile numai la nivel de "
               "total judet.",
    surseDeDate=[{"nume": "Cercetarea statistica privind costul fortei de "
                          "munca <<6263>>", "tip": "Surse statistice (INS)"}],
)


def test_describe_prints_full_text(monkeypatch, capsys):
    _fake_api(monkeypatch,
              extra={endpoints.matrix("FOM104D"): FOM104D_CU_TEXT})
    t.matrix("FOM104D").describe()
    iesire = capsys.readouterr().out

    assert "FOM104D" in iesire
    assert "DEFINITIE" in iesire and "METODOLOGIE" in iesire
    assert "SURSE" in iesire and "OBSERVATII" in iesire
    # capul definitiei
    assert "persoanele angajate cu contract" in iesire
    # coada definitiei: daca lipseste, textul a fost trunchiat
    assert "conform prevederilor legale in vigoare." in iesire
    assert len(DEFINITIE_LUNGA) > 1000
    # observatiile duc nota despre anul incomplet
    assert "anul 1990" in iesire
    # markerul INS <<6263>> nu e HTML si nu trebuie curatat ca atare
    assert "Cercetarea statistica privind costul fortei de munca <<6263>>" \
        in iesire


def test_describe_skips_empty_sections(monkeypatch, capsys):
    fara_text = dict(FOM104D, definitie="", metodologie="   ",
                     observatii="", surseDeDate=[])
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): fara_text})
    t.matrix("FOM104D").describe()
    iesire = capsys.readouterr().out
    assert "FOM104D" in iesire
    for titlu in ("DEFINITIE", "METODOLOGIE", "SURSE", "OBSERVATII"):
        assert titlu not in iesire


def test_options_without_argument_lists_dimensions(monkeypatch):
    _fake_api(monkeypatch)
    dims = t.matrix("FOM104D").options()
    assert len(dims) == 4
    assert dims[0] == "[0] Judete (teritoriu, 2 optiuni)"
    assert dims[1].startswith("[1] Localitati (teritoriu,")
    assert dims[2] == "[2] Ani (timp, 1 optiuni)"
    assert dims[3].startswith("[3] UM: Numar persoane (um,")
    # cu argument, comportamentul de dinainte
    assert list(t.matrix("FOM104D").options("Judete")) == ["TOTAL", "Alba"]


def test_find_and_search_are_distinct(monkeypatch):
    """find e simplu, search accepta filtre."""
    import inspect
    par_find = inspect.signature(t.find).parameters
    par_search = inspect.signature(t.search).parameters
    assert "level" not in par_find
    assert "level" in par_search
    assert t.find is not t.search
    # search merge si fara cuvant
    assert par_search["query"].default == ""


def test_search_without_query_walks_whole_catalogue(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text(json.dumps({
        "FOM104D": {"levels": ["national", "judet", "localitate"]},
        "SOM101B": {"levels": ["national", "judet"]},
        "FOM101A": {"levels": ["national", "judet"]},
    }), encoding="utf-8")
    _index_and_meta(monkeypatch, TOATE_META)

    assert len(t.search()) == 3
    assert [m.code for m in t.search(level="localitate")] == ["FOM104D"]


INDEX_COMPLET = {
    "FOM104D": {"levels": ["national", "judet", "localitate"],
                "periodicity": ["Anuala"], "has_caen": False,
                "domain": "A. STATISTICA SOCIALA"},
    "SOM101B": {"levels": ["national", "judet"],
                "periodicity": ["Lunara", "Anuala"], "has_caen": False,
                "domain": "A. STATISTICA SOCIALA"},
    "FOM101A": {"levels": ["national", "judet"],
                "periodicity": ["Anuala"], "has_caen": False,
                "domain": "A. STATISTICA SOCIALA"},
    "FOM104F": {"levels": ["national", "judet"],
                "periodicity": ["Trimestriala"], "has_caen": True,
                "domain": "B. STATISTICA ECONOMICA"},
}


def _index_pe_disc(monkeypatch, tmp_path, continut=INDEX_COMPLET):
    cale = _cache_in(monkeypatch, tmp_path)
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text(json.dumps(continut), encoding="utf-8")
    return cale


def _catalog_de_test(monkeypatch):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"}
                         for c in INDEX_COMPLET])


def test_search_filter_caen(monkeypatch, tmp_path):
    _index_pe_disc(monkeypatch, tmp_path)
    _catalog_de_test(monkeypatch)
    assert [m.code for m in t.search(caen=True)] == ["FOM104F"]
    assert sorted(m.code for m in t.search(caen=False)) == [
        "FOM101A", "FOM104D", "SOM101B"]
    assert len(t.search()) == 4          # caen=None ignora filtrul


def test_search_filter_domeniu_is_substring_and_diacritics_free(
        monkeypatch, tmp_path):
    _index_pe_disc(monkeypatch, tmp_path)
    _catalog_de_test(monkeypatch)
    # 'economic' prinde 'B. STATISTICA ECONOMICA', fara forma exacta
    assert [m.code for m in t.search(domeniu="economic")] == ["FOM104F"]
    assert len(t.search(domeniu="sociala")) == 3
    # diacriticele din cerere nu strica potrivirea
    assert [m.code for m in t.search(domeniu="ecOnOmică")] == ["FOM104F"]
    assert len(t.search(domeniu="socială")) == 3
    # un cuvant care chiar nu apare nu potriveste nimic
    assert list(t.search(domeniu="agricultura")) == []


def test_search_filter_periodicitate(monkeypatch, tmp_path):
    _index_pe_disc(monkeypatch, tmp_path)
    _catalog_de_test(monkeypatch)
    assert sorted(m.code for m in t.search(periodicitate="anual")) == [
        "FOM101A", "FOM104D", "SOM101B"]
    assert [m.code for m in t.search(periodicitate="lunar")] == ["SOM101B"]
    assert [m.code for m in t.search(periodicitate="trimestrial")] == ["FOM104F"]


def test_search_filters_combine(monkeypatch, tmp_path):
    _index_pe_disc(monkeypatch, tmp_path)
    _catalog_de_test(monkeypatch)
    assert [m.code for m in
            t.search(domeniu="economic", caen=True, level="judet")] == ["FOM104F"]
    # aceleasi filtre, dar cu un nivel pe care nu il are: nimic
    assert list(t.search(domeniu="economic", caen=True,
                         level="localitate")) == []
    # filtrele se combina si cu cuvantul cautat
    assert [m.code for m in t.search("FOM104F", caen=True)] == ["FOM104F"]
    assert list(t.search("SOM101B", caen=True)) == []


def test_search_results_carry_index_fields(monkeypatch, tmp_path):
    """Nivelele si periodicitatea vin din index, fara apel de retea."""
    _index_pe_disc(monkeypatch, tmp_path)
    apeluri = _index_and_meta(monkeypatch, TOATE_META)
    _catalog_de_test(monkeypatch)

    m = t.search(level="localitate")[0]
    assert m.code == "FOM104D"
    assert m.levels == ["national", "judet", "localitate"]
    assert m.periodicity == ["Anuala"]
    assert apeluri == []


def test_search_metadata_filter_triggers_build(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META | {"FOM104F": FOM104F})
    monkeypatch.setattr("builtins.input", lambda _: "d")

    rez = t.search(caen=True)
    assert cale.exists()
    # din fixture-urile de metadate, doar FOM104F are dimensiune CAEN
    assert [m.code for m in rez] == ["FOM104F"]


def test_build_index_stores_new_fields(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META | {"FOM104F": FOM104F})

    idx = t.build_index(confirm=False, progress=False)
    assert set(idx["FOM104D"]) == set(catalog.INDEX_FIELDS)
    assert idx["FOM104D"]["periodicity"] == ["Anuala"]
    assert idx["FOM104D"]["has_caen"] is False
    assert idx["FOM104F"]["has_caen"] is True
    assert idx["FOM104D"]["domain"] == "A. STATISTICA SOCIALA"
    assert json.loads(cale.read_text(encoding="utf-8"))["FOM104F"]["has_caen"]


def test_old_index_is_handled_gently(monkeypatch, tmp_path, capsys):
    """Un index vechi, doar cu levels, nu crapa; filtrele noi nu potrivesc."""
    vechi = {cod: {"levels": f["levels"]} for cod, f in INDEX_COMPLET.items()}
    _index_pe_disc(monkeypatch, tmp_path, vechi)
    _catalog_de_test(monkeypatch)

    # level merge in continuare, e singurul camp prezent
    assert [m.code for m in t.search(level="localitate")] == ["FOM104D"]
    iesire = capsys.readouterr().out
    assert "versiune mai veche" in iesire
    assert "build_index(refresh=True)" in iesire

    # filtrele pe campurile lipsa nu potrivesc nimic, dar nu arunca
    assert list(t.search(caen=True)) == []
    assert list(t.search(domeniu="economic")) == []
    assert list(t.search(periodicitate="anual")) == []


def test_filters_runs_with_index(monkeypatch, tmp_path, capsys):
    _index_pe_disc(monkeypatch, tmp_path)
    _fake_api(monkeypatch)
    t.filters()
    iesire = capsys.readouterr().out
    assert "level" in iesire and "localitate" in iesire
    assert "caen" in iesire
    assert "A. STATISTICA SOCIALA" in iesire     # din domains()
    assert "Trimestriala" in iesire              # periodicitati reale din index
    assert "t.search(domeniu='economic'" in iesire


def test_filters_runs_without_index(monkeypatch, tmp_path, capsys):
    _cache_in(monkeypatch, tmp_path)
    _fake_api(monkeypatch)
    t.filters()
    iesire = capsys.readouterr().out
    assert "Anuala" in iesire and "Lunara" in iesire   # exemple uzuale
    assert "Indexul nu exista inca" in iesire


def test_matrix_unknown_code(monkeypatch):
    _fake_api(monkeypatch)
    try:
        t.matrix("FOM101B")
    except ValueError as e:
        assert "FOM101B" in str(e) and "t.find" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru cod inexistent")


def test_matrix_code_is_normalized(monkeypatch):
    _fake_api(monkeypatch)
    assert t.matrix("  fom104d ").code == "FOM104D"


def test_get_json_non_json_response(monkeypatch):
    """INS raspunde 200 cu non-JSON; iese ValueError clar, nu JSONDecodeError."""
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(client.requests, "get", lambda url, **kw: FakeResp())
    try:
        client.get_json("http://exemplu/nimic", use_cache=False)
    except ValueError as e:
        assert type(e) is ValueError
        assert "nu e JSON" in str(e) and "http://exemplu/nimic" in str(e)
    else:
        raise AssertionError("trebuia ValueError")


def test_no_levels_when_nothing_is_territorial(monkeypatch):
    """Nici details, nici labelurile nu spun teritoriu, deci niciun nivel."""
    data = dict(
        FOM104D,
        details={"nomJud": 0, "nomLoc": 0, "matRegJ": 0, "matTime": 3,
                 "matCaen1": 0, "matCaen2": 0, "matSiruta": 0, "matMaxDim": 3},
        dimensionsMap=[
            {"dimCode": 1, "label": "Sexe", "options": [
                {"label": "Masculin", "nomItemId": 1, "offset": 1, "parentId": None}]},
            {"dimCode": 3, "label": "Ani", "options": [
                {"label": "Anul 2020", "nomItemId": 2, "offset": 1, "parentId": None}]},
            {"dimCode": 9, "label": "UM: Numar persoane", "options": [
                {"label": "Numar persoane", "nomItemId": 3, "offset": 1,
                 "parentId": None}]},
        ],
    )
    _fake_matrix(monkeypatch, data)
    m = t.matrix("FOM104D")
    assert m.levels == []
    assert [d.role for d in m.dimensions] == ["alt", "timp", "um"]
    assert m.has_siruta is False
