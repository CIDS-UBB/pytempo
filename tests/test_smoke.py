"""Teste offline: import, API public, căutare pe un index injectat."""
import pytempo as t
from pytempo import catalog, endpoints
from pytempo.chunking import split_options


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
