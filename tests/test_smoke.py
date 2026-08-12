"""Teste offline: import, API public, căutare pe un index injectat."""
import pandas as pd

import pytempo as t
from pytempo import catalog, chunking, client, endpoints, parse, territory
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
                codes=("FOM104D", "SOM101B", "FOM101A", "FOM104F")):
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
    assert territory.option_level("") == "judet"


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
    crumbs = t.matrix("FOM104D").where()
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


def test_matrixlist_html_has_no_levels_column(monkeypatch):
    """In liste nu aratam nivele: domeniile n-au, iar indicatorii ar cere
    cate un apel per rand."""
    _fake_api(monkeypatch)
    html_out = t.MatrixList([t.matrix("FOM104D")])._repr_html_()
    assert "FOM104D" in html_out
    assert "<tr><th>cod</th><th>nume</th></tr>" in html_out
    assert "<th>nivele</th>" not in html_out


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
    df = t.matrix("FOM101A").get()

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
        assert "localitate" in str(e) and "Disponibile" in str(e)
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


def test_size_guard_blocks_huge_pull(monkeypatch):
    """Fara filtru, o matrice mare nu mai pleaca la drum."""
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
    _capture_post(monkeypatch)
    m = t.matrix("SOM101B")
    assert 5 * 35 * 900 > MAX_CELLS
    try:
        m.get()
    except ValueError as e:
        # nu are dimensiune de localitati, deci nu poate fi spart pe judete
        assert "celule" in str(e) and "localitati" in str(e)
    else:
        raise AssertionError("trebuia ValueError de la paza de marime")

    # cu filtru pe nivel coboara sub prag si trece
    trimis = _capture_post(monkeypatch)
    m.get(level="judet")
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
    brut = t.matrix("SOM101B").get(level="judet")
    tidy = t.matrix("SOM101B").get(level="judet", tidy=True)
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
    """Un singur judet peste prag se mai sparge in grupuri."""
    _fake_api(monkeypatch, extra={endpoints.matrix("FOM104D"): FOM104D_MIC})
    m = t.matrix("FOM104D")
    # cu prag 2, judetul Alba (3 localitati x 2 ani = 6) nu incape intreg
    planuri = _plan_for(m, max_cells=2)
    alba = [p for p in planuri if p["encQuery"].startswith("3064:")]
    assert len(alba) == 1  # 3 localitati intr-un grup de 100
    monkeypatch.setattr(chunking, "COUNTY_CHUNK", 2)
    alba = [p for p in _plan_for(m, max_cells=2)
            if p["encQuery"].startswith("3064:")]
    assert [p["encQuery"].split(":")[1] for p in alba] == ["113,114", "115"]


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
    # cate o cerere per grup de parentId, doar cu localitatile grupului
    blocuri = sorted(p["encQuery"].split(":")[0] for p in planuri)
    assert blocuri == ["112", "113,114,115", "116"]


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
    assert len(planuri) == 3          # 250 localitati in grupuri de 100
    bucati = [p["encQuery"].split(":")[1].split(",") for p in planuri]
    assert [len(b) for b in bucati] == [100, 100, 50]
    # nicio localitate pierduta, niciuna repetata
    toate = [c for b in bucati for c in b]
    assert len(toate) == len(set(toate)) == 250


def test_level_filter_runs_before_planning(monkeypatch):
    """level reduce selectia inainte de planificare, deci nu se mai sparge."""
    _fake_api(monkeypatch)
    m = t.matrix("SOM101B")
    # fara filtru selectia depaseste un prag mic si nu are localitati de spart
    monkeypatch.setattr(chunking, "MAX_CELLS", 3)
    try:
        m.get()
    except ValueError as e:
        assert "localitati" in str(e)
    else:
        raise AssertionError("trebuia ValueError fara filtru")

    # cu filtru pe nivel incape intr-o singura cerere, deci nu se sparge
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return CSV_SOM101B

    monkeypatch.setattr(client, "post_pivot", fake_post)
    m.get(level="judet")
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
        assert nivel == "judet"   # option_level nu are alt raspuns pentru gol


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


def test_find_without_level_fetches_no_metadata(monkeypatch):
    apeluri = _index_and_meta(monkeypatch, {
        "FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A})
    rez = t.find("salariati")
    assert len(rez) == 3
    assert apeluri == []          # raspuns doar din indexul de nume


def test_find_with_level_filters_and_fetches(monkeypatch):
    apeluri = _index_and_meta(monkeypatch, {
        "FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A})
    rez = t.find("salariati", level="localitate")
    # doar FOM104D coboara la localitate
    assert [m.code for m in rez] == ["FOM104D"]
    assert set(apeluri) == {"FOM104D", "SOM101B", "FOM101A"}
    # metadatele sunt deja acolo, deci nivelele se pot afisa fara cost in plus
    assert rez[0].levels == ["national", "judet", "localitate"]


def test_find_with_level_judet(monkeypatch):
    _index_and_meta(monkeypatch, {
        "FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A})
    rez = t.find("salariati", level="judet")
    assert sorted(m.code for m in rez) == ["FOM101A", "FOM104D", "SOM101B"]


def test_find_with_level_stops_at_limit(monkeypatch):
    """Nu aduce metadate pentru tot catalogul, se opreste la limit."""
    apeluri = _index_and_meta(monkeypatch, {
        "FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A})
    rez = t.find("salariati", level="judet", limit=1)
    assert len(rez) == 1
    assert len(apeluri) == 1      # s-a oprit dupa prima potrivire


def test_find_unknown_level(monkeypatch):
    _fake_api(monkeypatch)
    try:
        t.find("salariati", level="comuna")
    except ValueError as e:
        assert "comuna" in str(e) and "Disponibile" in str(e)
    else:
        raise AssertionError("trebuia ValueError pentru nivel necunoscut")


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
