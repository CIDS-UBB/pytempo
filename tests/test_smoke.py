"""Offline tests: imports, public API, search over an injected index."""
import json

import pandas as pd

import pytempo as t
from pytempo import (catalog, chunking, client, endpoints, parse, schemas,
                     territory)
from pytempo.chunking import split_options
from pytempo.matrix import MAX_CELLS

# fixture shaped like the real FOM104D: two separate territorial
# dimensions (Judete and Localitati), time and unit of measure.
FOM104D = {
    "matrixName": "Numarul mediu al salariatilor pe judete si localitati",
    "definitie": "Numarul mediu al salariatilor",
    "metodologie": "Cercetare statistica",
    "observatii": "",
    "ultimaActualizare": "20-11-2025",
    "periodicitati": ["Anuala"],
    "surseDeDate": [{"nume": "Cercetarea statistica privind costul fortei de munca"}],
    # node names arrive with embedded HTML, as in the real API
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

# the options of a hierarchical territorial dimension, as in the real API:
# TOTAL, then macroregions, then regions, then counties
_IERARHIC = [
    {"label": "TOTAL", "nomItemId": 1, "offset": 1, "parentId": None},
    {"label": "MACROREGIUNEA UNU", "nomItemId": 2, "offset": 2, "parentId": 1},
    {"label": "Regiunea NORD-VEST", "nomItemId": 3, "offset": 3, "parentId": 2},
    {"label": "Bihor", "nomItemId": 4, "offset": 4, "parentId": 3},
    {"label": "Cluj", "nomItemId": 5, "offset": 5, "parentId": 3},
]

# SOM101B: nomJud and nomLoc are 0, but matRegJ points at dimension 3.
# Detection comes from details.
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

# FOM101A: matRegJ = 2, so also from details. A fixture true to reality.
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

# context('') is the whole tree flattened; top domains have level 0
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

# context(node) is a dict; matrix leaves have url == 'matrix'
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

    # two words: all of them have to match
    hits = t.search("salariatilor localitati")
    assert len(hits) == 1 and hits[0].code == "FOM104D"


def _fake_index(monkeypatch,
                codes=("FOM104D", "SOM101B", "FOM101A", "FOM104F",
                       "TMP1173")):
    """The catalogue, injected: matrix() checks it before fetching."""
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": c} for c in codes])


def _fake_matrix(monkeypatch, data=FOM104D):
    """Inject the matrix/{code} response. t.matrix is the function, not the
    module."""
    _fake_index(monkeypatch)
    monkeypatch.setattr(client, "get_json", lambda url, **kw: data)


def _fake_api(monkeypatch, extra=None):
    """Route by URL: matrix/{code}, context('') and context(node)."""
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
    # dim_index keeps the dimensionsMap order
    assert [d.dim_index for d in m.dimensions] == [0, 1, 2, 3]


# TMP1173: the label says 'Localitate', but matSiruta is 0 and the options
# are monitoring stations, not localities with a SIRUTA prefix
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
    """The label alone does not make a locality dimension."""
    _fake_api(monkeypatch, extra={endpoints.matrix("TMP1173"): TMP1173})
    m = t.matrix("TMP1173")
    statii = m.dimensions[1]
    assert statii.role == "teritoriu"          # stays territorial
    assert territory.is_locality_dimension(statii, m.details) is False
    # the levels come from the options, not from the label
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
    # no station carries a SIRUTA code or a settlement type, so those two
    # derived columns are not added at all
    assert f"{col}_siruta" not in tidy.columns
    assert f"{col}_tip" not in tidy.columns


def test_real_localities_still_detected(monkeypatch):
    """FOM104D has nomLoc set, so nothing changes for it."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    localitati = m.dimensions[1]
    assert territory.is_locality_dimension(localitati, m.details) is True
    assert m.levels == ["national", "judet", "localitate"]
    assert m.has_siruta is True


def test_localities_confirmed_by_siruta_prefixes(monkeypatch):
    """No nomLoc, but SIRUTA prefixes on the options: localities all the same."""
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
    # the national total is not always spelled 'TOTAL'
    assert territory.option_level("Nivel National") == "national"
    # county groupings and residuals are not counties
    assert territory.option_level("Arges, Valcea") == "necunoscut"
    assert territory.option_level("Extra-regiuni") == "necunoscut"
    # what is not in the real nomenclator no longer falls through to judet
    assert territory.option_level("BT-1 - Municipiul Botosani") == "necunoscut"
    assert territory.option_level("Punct de trecere Nadlac") == "necunoscut"
    assert territory.option_level("") == "necunoscut"


def test_levels_hierarchical_from_details(monkeypatch):
    """SOM101B: nomJud and nomLoc are 0, but matRegJ marks the dimension."""
    _fake_api(monkeypatch)
    m = t.matrix("SOM101B")
    assert m.levels == ["national", "macroregiune", "regiune", "judet"]
    assert [d.role for d in m.dimensions] == ["teritoriu", "timp", "um"]


def test_levels_hierarchical_from_label(monkeypatch):
    """The same result when details is silent: detection comes from the label.

    The real FOM101A has matRegJ = 2, so details would catch it. We set it to
    0 so only the label is left to do the work.
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
    # a locality's parentId is the county's nomItemId (Alba = 3064)
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
    # 'home' drops out (no code), and the anchor disappears with its text
    assert list(crumbs) == ["A. STATISTICA SOCIALA", "FORTA DE MUNCA", "SALARIATI"]
    assert repr(crumbs) == "A. STATISTICA SOCIALA > FORTA DE MUNCA > SALARIATI"


def test_related_filters_siblings(monkeypatch):
    _fake_api(monkeypatch)
    rel = t.matrix("FOM104D").related()
    # excludes the current indicator and sub nodes that are not matrices
    assert [m.code for m in rel] == ["FOM104A"]
    assert isinstance(rel, t.MatrixList)


def test_options_by_label_role_and_index(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    assert list(m.options("Judete")) == ["TOTAL", "Alba"]
    assert list(m.options("timp")) == ["Anul 1990"]
    assert list(m.options(3)) == ["Numar persoane"]
    # 'teritoriu' picks the finest dimension present
    assert m.options("teritoriu")[1] == "1017 MUNICIPIUL ALBA IULIA"
    assert list(m.options("Judete", limit=1)) == ["TOTAL"]


def test_options_unknown_dimension(monkeypatch):
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    try:
        m.options("nu exista")
    except ValueError as e:
        assert "Available" in str(e)
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
    """The column appears only when every element already knows its levels."""
    _fake_api(monkeypatch)
    lista = t.MatrixList([t.matrix("FOM104D")])   # metadate aduse
    html_out = lista._repr_html_()
    assert "<th>levels</th>" in html_out
    assert "judet, localitate" in html_out
    assert "[national, judet, localitate]" in repr(lista)

    # from the index, with no metadata: still known
    din_index = t.MatrixList([t.Matrix("X", "x", cached_levels=["judet"])])
    assert "<th>levels</th>" in din_index._repr_html_()
    # known to have none: the column stays, the cell is empty
    gol = t.MatrixList([t.Matrix("Y", "y", cached_levels=[])])
    assert "<th>levels</th>" in gol._repr_html_()


def test_matrixlist_hides_levels_when_any_unknown(monkeypatch):
    _fake_api(monkeypatch)
    # a plain find: code and name only, the levels are unknown
    necunoscut = t.MatrixList([t.Matrix("X", "x")])
    html_out = necunoscut._repr_html_()
    assert "<tr><th>code</th><th>name</th></tr>" in html_out
    assert "<th>levels</th>" not in html_out

    # lista mixta: un singur element necunoscut ascunde coloana
    mixta = t.MatrixList([t.matrix("FOM104D"), t.Matrix("X", "x")])
    assert "<th>levels</th>" not in mixta._repr_html_()

    # domains have no levels at all
    from pytempo.models import Node
    domenii = t.MatrixList([Node(code="1", name="A. STATISTICA SOCIALA")])
    assert "<th>levels</th>" not in domenii._repr_html_()


def test_level_literal_matches_level_order():
    """The Literal and the tuple have to stay in sync."""
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
    assert "unknown level 'judete'" in mesaj
    assert "national, macroregiune, regiune, judet, localitate" in mesaj
    assert "Did you mean 'judet'?" in mesaj


def test_unknown_level_without_suggestion():
    try:
        t.search(level="zzzzz")
    except ValueError as e:
        mesaj = str(e)
    else:
        raise AssertionError("trebuia ValueError")
    assert "unknown level 'zzzzz'" in mesaj
    assert "Available:" in mesaj
    assert "Did you mean" not in mesaj


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
        assert mesaj.startswith("unknown level 'judete'")
        assert "Available:" in mesaj
        assert "Did you mean 'judet'?" in mesaj
    # get also names the indicator and lists that indicator's levels
    assert "for FOM101A" in din_get
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
    """On a single indicator card the levels really are available."""
    _fake_api(monkeypatch)
    html_out = t.matrix("FOM104D")._repr_html_()
    assert "judet, localitate" in html_out
    assert "Localitati" in html_out


# CSV as pivot returns it: a space after each comma, decimal point, no
# quoting, an integer with no decimals (13544). Sparse: the combination
# (Feminin, Ilfov, Anul 1990) is missing as a whole row, not as a blank.
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
    # names come from the dimensions, not from the header INS cleaned
    assert df.columns.tolist() == [
        "Sexe", "Macroregiuni, regiuni de dezvoltare si judete", "Ani",
        "UM: Mii persoane", "Valoare"]
    assert str(df["Valoare"].dtype) == "float64"
    assert df["Valoare"].tolist() == [13216.9, 13544.0, 102.4, 6512.3, 96.1]
    # pandas 2 gives 'object' for text, pandas 3 gives 'str'; all that matters
    # is that it is not numeric
    assert str(df["Sexe"].dtype) in ("object", "str")
    assert df["Sexe"].tolist()[0] == "Total"


def test_parse_sparse_rows_are_absent_not_nan(monkeypatch):
    """A missing combination gives no NaN, the row simply does not exist."""
    _fake_api(monkeypatch)
    df = parse.pivot_csv_to_dataframe(CSV_FOM101A, t.matrix("FOM101A"))
    assert df["Valoare"].isna().sum() == 0
    lipsa = df[(df["Sexe"] == "Feminin")
               & (df["Macroregiuni, regiuni de dezvoltare si judete"] == "Ilfov")]
    assert len(lipsa) == 0


def test_parse_empty_csv_is_not_an_error(monkeypatch):
    """A response with no rows is legitimate, not a slipped column mapping."""
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
        assert "3 columns" in str(e) and "expected 5" in str(e)
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
        assert "is not numeric" in str(e)
    else:
        raise AssertionError("trebuia ValueError la Valoare ne-numerica")


def test_build_encquery():
    assert chunking.build_encquery([[105, 106], [112], [4247, 4266]]) == \
        "105,106:112:4247,4266"
    assert chunking.build_encquery([[1]]) == "1"


def test_get_builds_payload_and_parses(monkeypatch):
    """get() takes every option, in dimensionsMap order."""
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
    # four dimensions, so three dimension separators
    assert trimis["encQuery"].count(":") == 3
    assert trimis["encQuery"].split(":")[1] == "1,2,3,4,5"
    assert df.shape == (5, 5)


# the SOM101B fixture has 3 dimensions, so 4 columns
CSV_SOM101B = (
    "Macroregiuni  regiuni de dezvoltare si judete, Ani, UM: Numar persoane, Valoare\n"
    "Bihor, Anul 2020, Numar persoane, 12.5\n"
    "Cluj, Anul 2020, Numar persoane, 18.0\n"
)


def _capture_post(monkeypatch, csv_text=CSV_SOM101B):
    """Capture the payload sent to pivot, with no network."""
    trimis = {}

    def fake_post(payload, **kw):
        trimis.update(payload)
        return csv_text

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return trimis


def _dim_codes(encquery, index):
    return [int(c) for c in encquery.split(":")[index].split(",")]


def test_get_level_judet_filters_options(monkeypatch):
    """Counties only, without TOTAL, MACROREGIUNEA or Regiunea."""
    _fake_api(monkeypatch)
    trimis = _capture_post(monkeypatch)
    t.matrix("SOM101B").get(level="judet")
    # in the fixture territory is the first dimension, so the first encQuery block
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
        assert "unknown level 'localitate' for SOM101B" in str(e)
        assert "Available: national, macroregiune, regiune, judet" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru nivel inexistent")


def test_get_level_two_territorial_dimensions(monkeypatch):
    """FOM104D keeps county and locality separate, and a level now works.

    The level picks the active dimension and puts the other on its total.
    """
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")

    judete = m._build_selection(["judet"])
    assert judete[0] == [3064]        # the county, TOTAL left out
    assert judete[1] == [112]         # localities pinned to their total

    localitati = m._build_selection(["localitate"])
    assert localitati[0] == [112, 3064]          # counties stay whole
    assert localitati[1] == [113, 114]           # localities, without TOTAL


def test_big_matrix_without_localities_is_split(monkeypatch):
    """With no localities to split by, it splits on the largest dimension.
    Nothing fails with a size error any more."""
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
    # each request fits under the threshold
    for p in planuri:
        bucati = [bloc.split(",") for bloc in p["encQuery"].split(":")]
        produs = 1
        for b in bucati:
            produs *= len(b)
        assert produs <= MAX_CELLS
    # no option lost on the dimension that was split
    toate = [c for p in planuri for c in p["encQuery"].split(":")[2].split(",")]
    assert len(set(toate)) == 900

    # with a level filter it fits in a single request
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
    # communes carry no type prefix
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

    # nothing is lost: same rows, same order, original columns
    assert len(out) == len(df)
    assert list(out[terr]) == list(df[terr])
    assert out[terr][0] == "1017 MUNICIPIUL ALBA IULIA"
    assert list(out["Valoare"]) == list(df["Valoare"])

    assert out[f"{terr}_siruta"].tolist()[:3] == [1017, 1151, 2130]
    assert out[f"{terr}_siruta"][3] is pd.NA      # TOTAL has no SIRUTA
    assert out[f"{terr}_siruta"][6] is pd.NA      # nor does the county Cluj
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
    # tidy adds columns, not rows
    assert len(tidy) == len(brut)
    assert tidy.shape[1] > brut.shape[1]
    terr = "Macroregiuni, regiuni de dezvoltare si judete"
    assert f"{terr}_nivel" in tidy.columns
    assert "Ani_an" in tidy.columns
    assert list(tidy[f"{terr}_nivel"]) == ["judet", "judet"]
    assert tidy["Ani_an"].tolist() == [2020, 2020]


# FOM104D in miniature: two counties with their localities via parentId
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
    # 3 counties x 5 localities x 2 years = 30, so a threshold of 10 forces a split
    planuri = _plan_for(m, max_cells=10)
    assert len(planuri) == 3  # TOTAL, Alba, Arad

    pe_judet = {}
    for p in planuri:
        blocuri = p["encQuery"].split(":")
        pe_judet[blocuri[0]] = blocuri[1]
    # each request has a single county and only its own localities
    assert pe_judet["112"] == "112"
    assert pe_judet["3064"] == "113,114,115"
    assert pe_judet["3065"] == "116"
    # the other dimensions stay complete
    assert all(p["encQuery"].split(":")[2] == "4247,4266" for p in planuri)


def test_plan_requests_splits_a_big_county(monkeypatch):
    """A county that does not fit is split further, under the threshold."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    m = t.matrix("FOM104D")
    # with a threshold of 2, Alba (3 localities x 2 years = 6) does not fit whole
    alba = [p for p in _plan_for(m, max_cells=2)
            if p["encQuery"].startswith("3064:")]
    assert [p["encQuery"].split(":")[1] for p in alba] == ["113", "114", "115"]
    # a piece of one locality x 2 years does fit under the threshold
    assert all(p["encQuery"].split(":")[2] == "4247,4266" for p in alba)


def test_empty_dimension_is_rejected(monkeypatch):
    """A filter that matched nothing must not build a broken encQuery."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    selection = [[o.nom_item_id for o in d.options] for d in m.dimensions]
    selection[1] = []
    try:
        chunking.plan_requests(m, selection)
    except ValueError as e:
        assert "empty dimension" in str(e)
    else:
        raise AssertionError("an empty dimension should raise")


def test_standardize_survives_non_string_values(monkeypatch):
    """A territorial column holding numbers or NaN must not crash the parse."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    df = pd.DataFrame({
        m.dimensions[0].label.strip(): ["Alba", "Cluj"],
        m.dimensions[1].label.strip(): [1017, float("nan")],
        m.dimensions[2].label.strip(): ["Anul 1990"] * 2,
        m.dimensions[3].label.strip(): ["Numar persoane"] * 2,
        "Valoare": [1.0, 2.0],
    })
    out = parse.standardize(df, m)
    assert len(out) == 2
    loc = m.dimensions[1].label.strip()
    assert out[f"{loc}_nivel"][0] == "necunoscut"


def test_split_selection_fits_every_chunk():
    """Pieces are sized by how much room the other dimensions leave."""
    selectie = [list(range(10)), list(range(4)), [99]]   # 40 de celule
    bucati = chunking.split_selection(selectie, max_cells=8)
    assert all(chunking.cells(b) <= 8 for b in bucati)
    # nothing lost, nothing repeated: the pieces sum to exactly the selection
    assert sum(chunking.cells(b) for b in bucati) == 40
    acoperite = {(a, b_, c) for b in bucati
                 for a in b[0] for b_ in b[1] for c in b[2]}
    assert len(acoperite) == 40


def test_split_selection_recurses_when_one_option_is_still_too_big():
    """If not even a single option fits, it moves on to another dimension."""
    selectie = [list(range(5)), list(range(20))]        # 100 de celule
    bucati = chunking.split_selection(selectie, max_cells=6)
    assert all(chunking.cells(b) <= 6 for b in bucati)
    assert sum(chunking.cells(b) for b in bucati) == 100
    # it had to cut the second dimension too, not just the first
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
    # two rows per request, nothing lost when concatenating
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


# the same small FOM104D, but the county dimension has an odd label.
# Its role comes from details (nomJud = 1), not the label, and _county_index
# has to find it by matching the parentIds.
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
    assert m.dimensions[0].role == "teritoriu"   # from details, nomJud = 1

    planuri = _plan_for(m, max_cells=10)
    pe_judet = {p["encQuery"].split(":")[0]: p["encQuery"].split(":")[1]
                for p in planuri}
    assert pe_judet["3064"] == "113,114,115"
    assert pe_judet["3065"] == "116"


def test_county_index_absent_when_no_second_territorial_dimension(monkeypatch):
    """With no county dimension, the split happens on localities alone."""
    fara_judete = dict(
        FOM104D_MIC,
        details=dict(FOM104D_MIC["details"], nomJud=0),
        dimensionsMap=FOM104D_MIC["dimensionsMap"][1:],
    )
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): fara_judete})
    m = t.matrix("FOM104D")
    planuri = _plan_for(m, max_cells=4)
    # one request per parentId group; a group that does not fit is split further
    blocuri = sorted(p["encQuery"].split(":")[0] for p in planuri)
    assert blocuri == ["112", "113,114", "115", "116"]


def test_chunked_requests_keep_row_order(monkeypatch):
    """Concatenation keeps every row and the order of the requests."""
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
    # the county order from the plan is preserved in the result
    assert df["Judete"].tolist() == [
        "J112", "J112", "J3064", "J3064", "J3065", "J3065"]


def test_big_county_produces_several_requests(monkeypatch):
    """A county whose localities do not fit on their own triggers a split."""
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
    # 250 localities x 2 years: the piece is sized by the years left
    bucati = [p["encQuery"].split(":")[1].split(",") for p in planuri]
    assert [len(b) for b in bucati] == [50, 50, 50, 50, 50]
    assert all(len(b) * 2 <= 100 for b in bucati)
    # nicio localitate pierduta, niciuna repetata
    toate = [c for b in bucati for c in b]
    assert len(toate) == len(set(toate)) == 250


def test_level_filter_runs_before_planning(monkeypatch):
    """level trims the selection before planning, so no split is needed."""
    _fake_api(monkeypatch)
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return CSV_SOM101B

    monkeypatch.setattr(client, "post_pivot", fake_post)
    monkeypatch.setattr(chunking, "MAX_CELLS", 3)
    m = t.matrix("SOM101B")

    # without a filter the selection exceeds the small threshold and is split
    m.get(level=None, progress=False)
    assert len(cereri) > 1

    # with a level filter it fits in a single request
    cereri.clear()
    m.get(level="judet", progress=False)
    assert len(cereri) == 1
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"


def test_parse_territory_prefix_needs_a_space():
    """Matching is on prefix plus space, not on substring.

    'ORASENI DEAL' is a commune whose name starts with the letters of ORAS.
    """
    assert territory.parse_territory("5000 ORASENI DEAL") == \
        (5000, "localitate", "comuna", "ORASENI DEAL")
    assert territory.parse_territory("5001 COMUNESTI") == \
        (5001, "localitate", "comuna", "COMUNESTI")
    # the long prefix wins over the short one
    assert territory.parse_territory("5002 ORASUL NOU")[2] == "oras"
    assert territory.parse_territory("5002 ORASUL NOU")[3] == "NOU"
    assert territory.parse_territory("179132 SECTORUL 3") == \
        (179132, "localitate", "sector", "3")
    assert territory.parse_territory("179133 SECTOR 4")[2] == "sector"


def test_parse_territory_empty_and_blank():
    """It does not break on empty input; with no leading digits there is no
    SIRUTA."""
    for gol in ("", "   ", None):
        siruta, nivel, tip, nume = territory.parse_territory(gol)
        assert siruta is None and tip is None
        assert nume == ""
        assert nivel == "necunoscut"   # empty is neither a county nor anything else


def test_standardize_skips_empty_derived_columns(monkeypatch):
    """A county dimension gets only _nivel: counties have no SIRUTA, no type."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM104D")
    jud = m.dimensions[0].label.strip()      # 'Judete'
    loc = m.dimensions[1].label.strip()      # 'Localitati'
    df = pd.DataFrame({
        jud: ["TOTAL", "Alba"],
        loc: ["TOTAL", "1017 MUNICIPIUL ALBA IULIA"],
        m.dimensions[2].label.strip(): ["Anul 1990"] * 2,
        m.dimensions[3].label.strip(): ["Numar persoane"] * 2,
        "Valoare": [1.0, 2.0],
    })
    out = parse.standardize(df, m)

    # counties: the level is useful, the other three would be empty
    assert f"{jud}_nivel" in out.columns
    assert f"{jud}_siruta" not in out.columns
    assert f"{jud}_tip" not in out.columns
    assert f"{jud}_nume" not in out.columns
    # localities: all four carry something
    for sufix in ("_siruta", "_nivel", "_tip", "_nume"):
        assert f"{loc}{sufix}" in out.columns, sufix
    assert out[f"{loc}_siruta"].tolist()[1] == 1017


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
    """A result with no rows must not break standardization."""
    _fake_api(monkeypatch)
    m = t.matrix("FOM101A")
    gol = pd.DataFrame({d.label.strip(): [] for d in m.dimensions} |
                       {"Valoare": []})
    out = parse.standardize(gol, m)
    assert len(out) == 0
    # with no rows there is no evidence for the optional columns, so only the
    # level and the year, which are always added, show up
    assert f"{m.dimensions[1].label.strip()}_nivel" in out.columns
    assert f"{m.dimensions[1].label.strip()}_siruta" not in out.columns


def test_public_api_names_all_resolve():
    """No dead exports in __all__."""
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
    assert "FOM104D" in iesire and "dimensions" in iesire


# FOM104F: matCaen1 and matCaen2 are 0, but dimension 1 is clearly CAEN.
# The role has to come from the label, exactly as for territory.
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
    """With no flag in details, CAEN is caught from the label."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): FOM104F})
    m = t.matrix("FOM104F")
    assert [d.role for d in m.dimensions] == [
        "caen", "alt", "teritoriu", "timp", "um"]


def test_caen_role_from_details(monkeypatch):
    """With the flag set it is still 'caen', even if the label says nothing."""
    cu_flag = dict(
        FOM104F,
        details=dict(FOM104F["details"], matCaen1=1),
        dimensionsMap=[dict(FOM104F["dimensionsMap"][0], label="Activitati")]
        + FOM104F["dimensionsMap"][1:],
    )
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): cu_flag})
    assert t.matrix("FOM104F").dimensions[0].role == "caen"


def test_non_caen_dimension_stays_alt(monkeypatch):
    """Without 'caen' in the label and without a flag, it stays 'alt'."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104F"): FOM104F})
    m = t.matrix("FOM104F")
    assert m.dimensions[1].label == "Sexe"
    assert m.dimensions[1].role == "alt"


def _index_and_meta(monkeypatch, meta_by_code):
    """Injected index plus metadata per code; counts the metadata calls."""
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
    """Move the cache and the metadata index into a temporary directory.

    It also hides the packaged registry: that takes priority for the filters,
    so without this the tests about the older index would read the real one.
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
    assert apeluri == []          # answered from the name index alone


def test_find_returns_everything_without_limit(monkeypatch):
    _index_and_meta(monkeypatch, TOATE_META)
    assert len(t.find("salariati")) == 3
    assert len(t.find("salariati", limit=2)) == 2
    assert len(t.search("salariati")) == 3


def test_build_index_writes_file_and_skips_errors(monkeypatch, tmp_path,
                                                  capsys):
    cale = _cache_in(monkeypatch, tmp_path)
    _index_and_meta(monkeypatch, TOATE_META)

    # SOM101B fails on metadata: it is skipped, the build carries on
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
    assert "building the index: 3/3" in iesire
    assert "skipped" in iesire

    pe_disc = json.loads(cale.read_text(encoding="utf-8"))
    assert pe_disc == idx


def test_build_index_respects_refresh(monkeypatch, tmp_path):
    cale = _cache_in(monkeypatch, tmp_path)
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text('{"VECHI": {"levels": ["judet"]}}', encoding="utf-8")
    apeluri = _index_and_meta(monkeypatch, TOATE_META)

    # the file exists, so it does not rebuild and does not touch the network
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
    assert "not building" in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda _: "da")
    idx = t.build_index(progress=False)
    assert set(idx) == set(TOATE_META)
    assert cale.exists()


def test_build_index_refusal_without_stdin(monkeypatch, tmp_path):
    """With no stdin the question cannot be answered: treated as no."""
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
    assert apeluri == []          # the index answers, with no network

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
    assert "Without the metadata index I cannot filter" in capsys.readouterr().out


def test_search_unknown_level(monkeypatch):
    _fake_api(monkeypatch)
    try:
        t.search("salariati", level="comuna")
    except ValueError as e:
        assert "unknown level 'comuna'" in str(e) and "Available:" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru nivel necunoscut")


# a fixture with long texts, as INS has: the definition has several
# paragraphs and a distinctive closing sentence, to catch truncation
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
    assert "DEFINITION" in iesire and "METHODOLOGY" in iesire
    assert "SOURCES" in iesire and "OBSERVATIONS" in iesire
    # the head of the definition
    assert "persoanele angajate cu contract" in iesire
    # the tail of the definition: if missing, the text was truncated
    assert "conform prevederilor legale in vigoare." in iesire
    assert len(DEFINITIE_LUNGA) > 1000
    # the observations carry the note about the incomplete year
    assert "anul 1990" in iesire
    # the INS marker <<6263>> is not HTML and must not be cleaned as such
    assert "Cercetarea statistica privind costul fortei de munca <<6263>>" \
        in iesire


def test_describe_skips_empty_sections(monkeypatch, capsys):
    fara_text = dict(FOM104D, definitie="", metodologie="   ",
                     observatii="", surseDeDate=[])
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): fara_text})
    t.matrix("FOM104D").describe()
    iesire = capsys.readouterr().out
    assert "FOM104D" in iesire
    for titlu in ("DEFINITION", "METHODOLOGY", "SOURCES", "OBSERVATIONS"):
        assert titlu not in iesire


def test_options_without_argument_lists_dimensions(monkeypatch):
    _fake_api(monkeypatch)
    dims = t.matrix("FOM104D").options()
    assert len(dims) == 4
    assert dims[0] == "[0] Judete (teritoriu, 2 options)"
    assert dims[1].startswith("[1] Localitati (teritoriu,")
    assert dims[2] == "[2] Ani (timp, 1 options)"
    assert dims[3].startswith("[3] UM: Numar persoane (um,")
    # with an argument, the previous behaviour
    assert list(t.matrix("FOM104D").options("Judete")) == ["TOTAL", "Alba"]


def test_find_and_search_are_distinct(monkeypatch):
    """find e simplu, search accepta filtre."""
    import inspect
    par_find = inspect.signature(t.find).parameters
    par_search = inspect.signature(t.search).parameters
    assert "level" not in par_find
    assert "level" in par_search
    assert t.find is not t.search
    # search works with no keyword too
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
    assert len(t.search()) == 4          # caen=None ignores the filter


def test_search_filter_domeniu_is_substring_and_diacritics_free(
        monkeypatch, tmp_path):
    _index_pe_disc(monkeypatch, tmp_path)
    _catalog_de_test(monkeypatch)
    # 'economic' matches 'B. STATISTICA ECONOMICA', no exact wording needed
    assert [m.code for m in t.search(domeniu="economic")] == ["FOM104F"]
    assert len(t.search(domeniu="sociala")) == 3
    # diacritics in the request do not break matching
    assert [m.code for m in t.search(domeniu="ecOnOmică")] == ["FOM104F"]
    assert len(t.search(domeniu="socială")) == 3
    # a word that really does not appear matches nothing
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
    # the same filters, but with a level it does not have: nothing
    assert list(t.search(domeniu="economic", caen=True,
                         level="localitate")) == []
    # the filters combine with the search word too
    assert [m.code for m in t.search("FOM104F", caen=True)] == ["FOM104F"]
    assert list(t.search("SOM101B", caen=True)) == []


def test_search_results_carry_index_fields(monkeypatch, tmp_path):
    """Levels and periodicity come from the index, with no network call."""
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
    # of the metadata fixtures, only FOM104F has a CAEN dimension
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
    """An older index, with levels only, does not break; new filters match
    nothing."""
    vechi = {cod: {"levels": f["levels"]} for cod, f in INDEX_COMPLET.items()}
    _index_pe_disc(monkeypatch, tmp_path, vechi)
    _catalog_de_test(monkeypatch)

    # level still works, it is the only field present
    assert [m.code for m in t.search(level="localitate")] == ["FOM104D"]
    iesire = capsys.readouterr().out
    assert "older version" in iesire
    assert "build_index(refresh=True)" in iesire

    # filters on missing fields match nothing, but do not raise
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
    assert "A. STATISTICA SOCIALA" in iesire     # from domains()
    assert "Trimestriala" in iesire              # real periodicities from the index
    assert "t.search(domeniu='economic'" in iesire


def test_filters_runs_without_index(monkeypatch, tmp_path, capsys):
    _cache_in(monkeypatch, tmp_path)
    _fake_api(monkeypatch)
    t.filters()
    iesire = capsys.readouterr().out
    assert "Anuala" in iesire and "Lunara" in iesire   # common examples
    assert "There is no index yet" in iesire


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
    """INS answers 200 with non JSON; a clear ValueError comes out, not a
    JSONDecodeError."""
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
        assert "is not JSON" in str(e) and "http://exemplu/nimic" in str(e)
    else:
        raise AssertionError("trebuia ValueError")


def test_no_levels_when_nothing_is_territorial(monkeypatch):
    """Neither details nor the labels say territory, so there is no level."""
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
