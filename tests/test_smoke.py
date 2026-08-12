"""Teste offline: import, API public, căutare pe un index injectat."""
import pytempo as t
from pytempo import catalog, chunking, client, endpoints, parse, territory
from pytempo.chunking import split_options

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


def _fake_index(monkeypatch, codes=("FOM104D", "SOM101B", "FOM101A")):
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
