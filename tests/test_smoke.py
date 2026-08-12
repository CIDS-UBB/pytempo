"""Teste offline: import, API public, căutare pe un index injectat."""
import pytempo as t
from pytempo import catalog, client, endpoints, territory
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
        "matCaen1": 0, "matCaen2": 0,
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

# SOM101B: nomJud si nomLoc sunt 0, desi o dimensiune contine judete.
# Regula determinista din details nu ii da nivel teritorial.
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
                "matCaen2": 0, "matSiruta": 0, "matMaxDim": 5},
    "dimensionsMap": [
        {"dimCode": 3, "label": "Macroregiuni, regiuni de dezvoltare si judete",
         "options": [{"label": "TOTAL", "nomItemId": 1, "offset": 1, "parentId": None}]},
        {"dimCode": 4, "label": "Ani", "options": [
            {"label": "Anul 2020", "nomItemId": 2, "offset": 1, "parentId": None}]},
        {"dimCode": 5, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 3, "offset": 1, "parentId": None}]},
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


def _fake_matrix(monkeypatch, data=FOM104D):
    """Injecteaza raspunsul matrix/{cod}. t.matrix e functia, nu modulul."""
    monkeypatch.setattr(client, "get_json", lambda url, **kw: data)


def _fake_api(monkeypatch, extra=None):
    """Ruteaza dupa URL: matrix/{cod}, context('') si context(nod)."""
    routes = {
        endpoints.matrix("FOM104D"): FOM104D,
        endpoints.matrix("SOM101B"): SOM101B,
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
    assert [d.role for d in m.dimensions] == ["judet", "localitate", "timp", "um"]
    # dim_index pastreaza ordinea din dimensionsMap
    assert [d.dim_index for d in m.dimensions] == [0, 1, 2, 3]


def test_levels_and_siruta(monkeypatch):
    _fake_matrix(monkeypatch)
    m = t.matrix("FOM104D")
    assert m.levels == ["judet", "localitate"]
    assert m.has_siruta is True


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
    assert d["levels"] == ["judet", "localitate"]
    assert d["has_siruta"] is True
    assert d["dimensions"][1] == {
        "index": 1, "code": 2, "label": "Localitati", "role": "localitate",
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


def test_matrixlist_html(monkeypatch):
    _fake_api(monkeypatch)
    html_out = t.MatrixList([t.matrix("FOM104D")])._repr_html_()
    assert "<table>" in html_out and "FOM104D" in html_out
    assert "judet, localitate" in html_out


def test_roles_without_territory(monkeypatch):
    """Fara nomJud/nomLoc in details nu se inventeaza nivele teritoriale."""
    data = dict(FOM104D, details=dict(FOM104D["details"], nomJud=0, nomLoc=0,
                                      matSiruta=0))
    _fake_matrix(monkeypatch, data)
    m = t.matrix("FOM104D")
    assert m.levels == []
    assert m.has_siruta is False
