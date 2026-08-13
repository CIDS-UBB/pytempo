"""Teste offline pentru registrul de scheme. Fara retea, cu fixture-uri."""
import json
import sys

import pytest

import pytempo as t
from pytempo import catalog, client, endpoints, schemas

from .test_smoke import FOM101A, FOM104D, FOM104F, SOM101B


def _fake_api(monkeypatch, meta):
    """Ruteaza matrix/{cod} si numara apelurile."""
    apeluri = []
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for cod, date in meta.items():
            if url == endpoints.matrix(cod):
                apeluri.append(cod)
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    return apeluri


TOATE = {"FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A,
         "FOM104F": FOM104F}


# ---------------------------------------------------------------- classify

def test_classify_judet_localitate():
    assert schemas.classify({"dims": [{"role": "teritoriu"}],
                             "has_localities": True, "has_caen": False}) == \
        "judet_localitate"
    # localitatile bat CAEN-ul: familia se da dupa cazul cel mai greu
    assert schemas.classify({"dims": [{"role": "teritoriu"}],
                             "has_localities": True, "has_caen": True}) == \
        "judet_localitate"


def test_classify_teritorial_caen_and_simplu():
    baza = {"dims": [{"role": "teritoriu"}, {"role": "caen"}],
            "has_localities": False}
    assert schemas.classify(dict(baza, has_caen=True)) == "teritorial_caen"
    assert schemas.classify(dict(baza, has_caen=False)) == "teritorial_simplu"


def test_classify_neteritorial():
    assert schemas.classify({"dims": [{"role": "timp"}, {"role": "um"}],
                             "has_localities": False,
                             "has_caen": False}) == "neteritorial"


def test_classify_alt_when_no_dimensions():
    assert schemas.classify({"dims": [], "has_localities": False,
                             "has_caen": False}) == "alt"
    assert schemas.classify({}) == "alt"


def test_classify_covers_every_family_name():
    """Fiecare familie declarata trebuie sa fie produsa de classify."""
    produse = {
        schemas.classify({"dims": [{"role": "teritoriu"}],
                          "has_localities": True}),
        schemas.classify({"dims": [{"role": "teritoriu"}],
                          "has_localities": False, "has_caen": True}),
        schemas.classify({"dims": [{"role": "teritoriu"}],
                          "has_localities": False, "has_caen": False}),
        schemas.classify({"dims": [{"role": "timp"}], "has_localities": False,
                          "has_caen": False}),
        schemas.classify({"dims": []}),
    }
    assert produse == set(schemas.FAMILIES)


# ------------------------------------------------------------ build_registry

def test_build_registry_writes_full_entries(monkeypatch, tmp_path):
    _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"
    date = schemas.build_registry(confirm=False, progress=False, path=cale)

    assert date["registry_version"] == schemas.REGISTRY_VERSION
    assert set(date["entries"]) == set(TOATE)

    e = date["entries"]["FOM104D"]
    for camp in ("name", "endpoint", "dims", "levels", "has_localities",
                 "has_caen", "has_sex", "has_siruta", "total_cells",
                 "periodicity", "domain", "last_updated", "family",
                 "fetched_at", "status"):
        assert camp in e, camp
    assert e["status"] == "ok"
    assert e["endpoint"].endswith("matrix/FOM104D")
    assert e["family"] == "judet_localitate"
    assert e["has_localities"] is True
    assert e["has_siruta"] is True
    assert e["levels"] == ["national", "judet", "localitate"]
    assert e["total_cells"] == 2 * 3 * 1 * 1
    assert e["domain"] == "A. STATISTICA SOCIALA"
    assert [d["label"] for d in e["dims"]][:2] == ["Judete", "Localitati"]

    # familiile celorlalti
    assert date["entries"]["SOM101B"]["family"] == "teritorial_simplu"
    assert date["entries"]["FOM104F"]["family"] == "teritorial_caen"
    assert date["entries"]["FOM104F"]["has_caen"] is True
    assert date["entries"]["FOM104F"]["has_sex"] is True

    pe_disc = json.loads(cale.read_text(encoding="utf-8"))
    assert pe_disc == date


def test_build_registry_records_errors_without_stopping(monkeypatch, tmp_path):
    """Un endpoint mort e notat, nu opreste recensamantul."""
    _fake_api(monkeypatch, TOATE)
    # pytempo.matrix e functia; modulul se ia din sys.modules
    matrix_mod = sys.modules["pytempo.matrix"]
    real = matrix_mod.matrix

    def stricat(cod, **kw):
        if cod == "SOM101B":
            raise ValueError("endpoint mort")
        return real(cod, **kw)

    monkeypatch.setattr(matrix_mod, "matrix", stricat)
    date = schemas.build_registry(confirm=False, progress=False,
                                  path=tmp_path / "r.json")

    assert date["entries"]["SOM101B"]["status"].startswith("error:")
    assert "endpoint mort" in date["entries"]["SOM101B"]["status"]
    assert date["entries"]["SOM101B"]["family"] == "alt"
    # ceilalti au trecut
    assert date["entries"]["FOM104D"]["status"] == "ok"
    assert date["entries"]["FOM104F"]["status"] == "ok"


def test_build_registry_incremental_skips_known(monkeypatch, tmp_path):
    apeluri = _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"

    schemas.build_registry(confirm=False, progress=False, path=cale)
    assert sorted(apeluri) == sorted(TOATE)

    apeluri.clear()
    schemas.build_registry(confirm=False, progress=False, path=cale)
    assert apeluri == []          # nimic nu se re-aduce

    # un cod nou intra, restul raman
    apeluri.clear()
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": c} for c in list(TOATE) + ["NOU"]])
    date = schemas.build_registry(confirm=False, progress=False, path=cale)
    assert apeluri == ["NOU"] or date["entries"]["NOU"]["status"].startswith(
        "error:")
    assert len(date["entries"]) == len(TOATE) + 1


def test_build_registry_refresh_redoes_everything(monkeypatch, tmp_path):
    apeluri = _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"
    schemas.build_registry(confirm=False, progress=False, path=cale)
    apeluri.clear()

    schemas.build_registry(confirm=False, progress=False, refresh=True,
                           path=cale)
    assert sorted(apeluri) == sorted(TOATE)


def test_build_registry_asks_before_uncached_work(monkeypatch, tmp_path):
    _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"
    # cache-ul e gol, deci toate metadatele ar veni din retea
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path / "gol")
    monkeypatch.setattr("builtins.input", lambda _: "n")

    date = schemas.build_registry(progress=False, path=cale)
    assert date["entries"] == {}
    assert not cale.exists()


# ---------------------------------------------------------------- versiune

def test_unknown_registry_version_is_clear(tmp_path):
    cale = tmp_path / "registry.json"
    cale.write_text('{"registry_version": 99, "entries": {}}',
                    encoding="utf-8")
    with pytest.raises(ValueError) as info:
        schemas.load_registry(cale)
    assert "registry_version=99" in str(info.value)
    assert "build_registry(refresh=True)" in str(info.value)


def test_missing_registry_returns_none(tmp_path):
    assert schemas.load_registry(tmp_path / "nu_exista.json") is None


# ------------------------------------------------------------------ report

def test_report_runs(monkeypatch, tmp_path, capsys):
    _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"
    date = schemas.build_registry(confirm=False, progress=False, path=cale)
    capsys.readouterr()

    schemas.report(date)
    iesire = capsys.readouterr().out
    assert "judet_localitate" in iesire
    assert "teritorial_caen" in iesire
    assert "A. STATISTICA SOCIALA" in iesire
    assert "cu SIRUTA" in iesire
    assert "erori" in iesire


def test_report_without_registry(tmp_path, capsys):
    schemas.report(path=tmp_path / "nu_exista.json")
    assert "Nu exista registry.json" in capsys.readouterr().out


# ------------------------------------------------- migrarea blanda in search

def test_search_prefers_registry(monkeypatch, tmp_path):
    _fake_api(monkeypatch, TOATE)
    cale = tmp_path / "registry.json"
    schemas.build_registry(confirm=False, progress=False, path=cale)
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH", cale)
    # niciun levels_index.json vechi
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path / "data" / "raw")

    assert [m.code for m in t.search(level="localitate")] == ["FOM104D"]
    assert [m.code for m in t.search(caen=True)] == ["FOM104F"]


def test_search_falls_back_to_levels_index(monkeypatch, tmp_path):
    """Fara registru, filtrele merg mai departe pe indexul vechi."""
    _fake_api(monkeypatch, TOATE)
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH",
                        tmp_path / "nu_exista.json")
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path / "data" / "raw")
    vechi = tmp_path / "data" / catalog.INDEX_FILE
    vechi.parent.mkdir(parents=True, exist_ok=True)
    vechi.write_text(json.dumps({
        "FOM104D": {"levels": ["judet", "localitate"], "periodicity": [],
                    "has_caen": False, "domain": ""}}), encoding="utf-8")

    assert [m.code for m in t.search(level="localitate")] == ["FOM104D"]
