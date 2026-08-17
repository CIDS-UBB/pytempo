"""Offline tests for get as a plan executor and the what/where/how trio."""
import sys

import pytempo as t
import pytempo.schemas.validate  # noqa: F401
from pytempo import catalog, chunking, client, endpoints, schemas

from .test_smoke import (CSV_FOM104D, CSV_SOM101B, FOM101A, FOM104D,
                         FOM104D_MIC, FOM104F, SOM101B, TMP1173)

TOATE = {"FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A,
         "FOM104F": FOM104F, "TMP1173": TMP1173}


def _api(monkeypatch, meta=TOATE):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for cod, date in meta.items():
            if url == endpoints.matrix(cod):
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


def _registry(monkeypatch, tmp_path, meta=TOATE):
    _api(monkeypatch, meta)
    cale = tmp_path / "registry.json"
    schemas.build_registry(confirm=False, progress=False, path=cale)
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH", cale)
    return cale


def _post(monkeypatch, csv_by_code):
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return csv_by_code[payload["matCode"]]

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return cereri


CSV = {"SOM101B": CSV_SOM101B, "FOM104D": CSV_FOM104D}

# an indicator with no territorial dimension at all
NETERITORIAL = {
    "matrixName": "AMIGO - Someri BIM pe grupe de varsta si sexe",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "01-03-2026",
    "periodicitati": ["Trimestriala"], "surseDeDate": [],
    "ancestors": [{"name": "A. STATISTICA SOCIALA", "code": "1"}],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 3, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 0, "matMaxDim": 4,
                "matUMSpec": 0},
    "dimensionsMap": [
        {"dimCode": 1, "label": "Grupe de varsta", "options": [
            {"label": "Total", "nomItemId": 70, "offset": 1, "parentId": None},
            {"label": "15-24 ani", "nomItemId": 71, "offset": 2,
             "parentId": None}]},
        {"dimCode": 2, "label": "Sexe", "options": [
            {"label": "Total", "nomItemId": 72, "offset": 1, "parentId": None}]},
        {"dimCode": 3, "label": "Perioade", "options": [
            {"label": "Anul 2024", "nomItemId": 73, "offset": 1,
             "parentId": None}]},
        {"dimCode": 4, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 74, "offset": 1,
             "parentId": None}]},
    ],
}


# ------------------------------------------------------- get ca executor

def test_get_uses_default_level_from_plan(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    cereri = _post(monkeypatch, CSV)
    df = t.matrix("SOM101B").get()

    # the plan says judet, so only counties are requested
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"
    iesire = capsys.readouterr().out
    assert "level judet (the finest)" in iesire
    # the default drops the coarser levels, so it says how to get them back
    assert "use get(level=None)" in iesire
    assert "national, macroregiune and regiune" in iesire
    # tidy is the default now
    assert any(c.endswith("_nivel") for c in df.columns)


def test_get_raw_gives_untouched_columns(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    _post(monkeypatch, CSV)
    m = t.matrix("SOM101B")
    brut = m.get(raw=True, progress=False)
    curat = m.get(progress=False)
    assert brut.shape[1] < curat.shape[1]
    assert not any(c.endswith("_nivel") for c in brut.columns)
    # tidy=False does the same thing
    assert m.get(tidy=False, progress=False).shape[1] == brut.shape[1]


def test_get_level_none_takes_everything(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    cereri = _post(monkeypatch, CSV)
    t.matrix("SOM101B").get(level=None, progress=False)
    assert cereri[0]["encQuery"].split(":")[0] == "1,2,3,4,5"


def test_get_explicit_levels_beat_the_default(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    cereri = _post(monkeypatch, CSV)
    t.matrix("SOM101B").get(levels=["national", "regiune"], progress=False)
    assert cereri[0]["encQuery"].split(":")[0] == "1,3"


def test_get_on_localities_does_not_raise(monkeypatch, tmp_path):
    """The default path on county plus locality works, through by_county."""
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    cereri = _post(monkeypatch, CSV)

    df = t.matrix("FOM104D").get(progress=False)
    assert len(cereri) == 3            # one county each
    assert len(df) == 6
    assert "Localitati_siruta" in df.columns


def test_level_judet_on_two_territorial_dimensions(monkeypatch, tmp_path):
    """Counties become active, localities go to TOTAL, in one request."""
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    cereri = _post(monkeypatch, CSV)
    t.matrix("FOM104D").get(level="judet", progress=False)

    assert len(cereri) == 1
    judete, localitati = cereri[0]["encQuery"].split(":")[:2]
    assert judete == "3064,3065"     # the real counties, no TOTAL
    assert localitati == "112"       # localities pinned to their total


def test_level_localitate_keeps_the_county_dimension_whole(monkeypatch,
                                                           tmp_path):
    """Pinning counties to TOTAL returns nothing, so they stay whole.

    Verified against INS: county TOTAL crossed with real localities gives zero
    rows, because the data is keyed by the real pair.
    """
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    cereri = _post(monkeypatch, CSV)
    t.matrix("FOM104D").get(level="localitate", progress=False)

    # one request per county group, each pairing a county with its own
    # localities, and never the locality TOTAL
    pe_judet = {p["encQuery"].split(":")[0]: p["encQuery"].split(":")[1]
                for p in cereri}
    assert pe_judet == {"3064": "113,114,115", "3065": "116"}
    assert all("112" not in blocuri for blocuri in pe_judet.values())


def test_level_national_puts_both_dimensions_on_total(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    cereri = _post(monkeypatch, CSV)
    t.matrix("FOM104D").get(level="national", progress=False)
    assert cereri[0]["encQuery"].split(":")[:2] == ["112", "112"]


def test_level_none_still_takes_everything(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 1000)
    cereri = _post(monkeypatch, CSV)
    t.matrix("FOM104D").get(level=None, progress=False)
    blocuri = cereri[0]["encQuery"].split(":")
    assert blocuri[0] == "112,3064,3065"
    assert blocuri[1] == "112,113,114,115,116"


def test_unknown_level_on_two_dimensions_still_raises(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    _post(monkeypatch, CSV)
    try:
        t.matrix("FOM104D").get(level="regiune", progress=False)
    except ValueError as e:
        assert "unknown level 'regiune'" in str(e)
        assert "localitate" in str(e)
    else:
        raise AssertionError("a level it does not have should raise")


def test_how_offers_levels_on_two_territorial_dimensions(monkeypatch, tmp_path,
                                                         capsys):
    _registry(monkeypatch, tmp_path)
    t.matrix("FOM104D").how()
    iesire = capsys.readouterr().out
    assert "m.get(level='judet')" in iesire
    assert "m.get(level='national')" in iesire
    assert "puts the other on TOTAL" in iesire


def test_get_neteritorial_has_no_territorial_filter(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    csv_tmp = ("Categorii de emisii, Statii de monitorizare de tip fond urban "
               "- Localitate, Ani, Unitati de masura, Valoare\n"
               "Total, BT-1 - Municipiul Botosani, Anul 2024, Micrograme, 26.2\n")
    cereri = _post(monkeypatch, {"TMP1173": csv_tmp})
    t.matrix("TMP1173").get(progress=False)
    # the plan has no usable default_level, so every option is requested
    assert cereri[0]["encQuery"].split(":")[1] == "61,62,63"


def test_get_over_the_limit_sends_you_to_download(monkeypatch, tmp_path):
    """A big plan stops before the first request and names the way out.

    It used to ask at the keyboard, which hangs in a notebook and answers
    itself with a no under pytest.
    """
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 2)
    # pytempo.matrix is the function; the module comes from sys.modules
    monkeypatch.setattr(sys.modules["pytempo.matrix"], "POLITE_REQUESTS", 2)
    cereri = _post(monkeypatch, CSV)

    try:
        t.matrix("FOM104D").get(progress=False)
    except ValueError as e:
        mesaj = str(e)
        assert "m.download(" in mesaj
        assert "get(confirm=False)" in mesaj
        assert "Nothing has been downloaded yet" in mesaj
    else:
        raise AssertionError("trebuia sa se opreasca inainte de descarcare")
    assert cereri == []          # niciun request trimis

    # confirm=False is still the way out for anyone who knows what they do
    t.matrix("FOM104D").get(progress=False, confirm=False)
    assert len(cereri) > 2


def test_get_falls_back_without_registry(monkeypatch, tmp_path):
    _api(monkeypatch)
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH",
                        tmp_path / "nu_exista.json")
    cereri = _post(monkeypatch, CSV)
    t.matrix("SOM101B").get(progress=False)
    # the plan is computed at runtime, so counties still come out
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"


def test_progress_auto_is_quiet_for_one_request(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    _post(monkeypatch, CSV)
    t.matrix("SOM101B").get()
    iesire = capsys.readouterr().out
    assert "1 request" in iesire
    assert "1/1" not in iesire       # no per request progress


# --------------------------------------------------------- what/where/how

def test_what_runs_on_every_family(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    for cod in TOATE:
        t.matrix(cod).what()
        iesire = capsys.readouterr().out
        assert cod in iesire


def test_what_takes_only_the_first_sentence(monkeypatch, tmp_path, capsys):
    lung = dict(FOM104D, definitie="Prima fraza scurta. A doua fraza, mai "
                                   "lunga, care nu trebuie sa apara.")
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=lung))
    t.matrix("FOM104D").what()
    iesire = capsys.readouterr().out
    assert "Prima fraza scurta." in iesire
    assert "A doua fraza" not in iesire


def test_what_flags_years_in_observations(monkeypatch, tmp_path, capsys):
    cu_ani = dict(FOM104D, observatii="Datele pentru anul 1990 sunt "
                                      "disponibile numai la nivel de judet.")
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=cu_ani))
    t.matrix("FOM104D").what()
    iesire = capsys.readouterr().out
    assert "1990" in iesire and "series breaks" in iesire


def test_where_shows_coverage(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    t.matrix("SOM101B").where()
    iesire = capsys.readouterr().out
    assert "domain" in iesire
    assert "territory" in iesire
    assert "judet" in iesire
    assert "SIRUTA" in iesire
    assert "time" in iesire and "2020" in iesire


def test_where_says_when_not_territorial(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    fara = t.matrix("FOM101A")
    # remove its territorial dimension, leaving a non territorial one
    fara.dimensions = [d for d in fara.dimensions if d.role != "teritoriu"]
    fara.where()
    assert "not territorial" in capsys.readouterr().out


def test_how_lists_only_its_own_levels(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    t.matrix("SOM101B").how()
    iesire = capsys.readouterr().out
    assert "m.get()" in iesire
    for nivel in ("national", "macroregiune", "regiune", "judet"):
        assert nivel in iesire
    # SOM101B does not reach locality level, so we do not suggest it
    assert "localitate" not in iesire
    assert "raw=True" in iesire


def test_how_warns_when_expensive(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    cale = schemas.build.REGISTRY_PATH
    date = schemas.load_registry(cale)
    date["entries"]["SOM101B"]["fetch_plan"]["est_requests"] = 530
    sys.modules["pytempo.schemas.validate"]._save(date, cale)

    t.matrix("SOM101B").how()
    iesire = capsys.readouterr().out
    assert "530" in iesire and "WARNING" in iesire
    assert "m.download(folder=" in iesire


def test_how_explains_the_two_dimension_semantics(monkeypatch, tmp_path,
                                                  capsys):
    """FOM104D keeps county and locality separate, and how() says what that
    means for a level."""
    _registry(monkeypatch, tmp_path)
    t.matrix("FOM104D").how()
    iesire = capsys.readouterr().out
    assert "separate dimensions" in iesire
    assert "which one is active" in iesire


def test_unknown_only_levels_mean_no_territorial_filter(monkeypatch, tmp_path):
    """TMP1173: its only level is 'necunoscut', so get() takes everything."""
    cale = _registry(monkeypatch, tmp_path)
    fisa = schemas.load_registry(cale)["entries"]["TMP1173"]
    assert fisa["levels"] == ["necunoscut"]
    assert fisa["fetch_plan"]["default_level"] is None

    csv_tmp = ("Categorii de emisii, Statii de monitorizare de tip fond urban "
               "- Localitate, Ani, Unitati de masura, Valoare\n"
               "Total, BT-1 - Municipiul Botosani, Anul 2024, Micrograme, 26.2\n")
    cereri = _post(monkeypatch, {"TMP1173": csv_tmp})
    t.matrix("TMP1173").get(progress=False)          # nu arunca
    assert cereri[0]["encQuery"].split(":")[1] == "61,62,63"


def test_mixed_levels_ignore_unknown_when_picking_finest():
    """A real level beats 'necunoscut' when picking the finest one."""
    plan = schemas.plan_for({
        "dims": [{"label": "Judete", "role": "teritoriu", "n_options": 50}],
        "levels": ["national", "macroregiune", "regiune", "judet",
                   "necunoscut"],
        "total_cells": 50, "family": "teritorial_simplu"})
    assert plan["default_level"] == "judet"


def test_how_explains_when_level_filter_does_not_apply(monkeypatch, tmp_path,
                                                       capsys):
    _registry(monkeypatch, tmp_path)
    # 'necunoscut' only: the names do not fit the nomenclator
    t.matrix("TMP1173").how()
    iesire = capsys.readouterr().out
    assert "does not apply here" in iesire and "get() takes everything" in iesire
    assert "m.get(level=" not in iesire


def test_non_territorial_get_and_how(monkeypatch, tmp_path, capsys):
    """A non territorial indicator has nothing to filter: get() takes everything
    and how() says so."""
    _registry(monkeypatch, tmp_path, dict(TOATE, AMG130A=NETERITORIAL))
    fisa = schemas.load_registry(schemas.build.REGISTRY_PATH)["entries"]
    assert fisa["AMG130A"]["levels"] == []
    assert fisa["AMG130A"]["fetch_plan"]["default_level"] is None

    csv = ("Grupe de varsta, Sexe, Perioade, UM: Numar persoane, Valoare\n"
           "Total, Total, Anul 2024, Numar persoane, 100.0\n")
    cereri = _post(monkeypatch, {"AMG130A": csv})
    t.matrix("AMG130A").get(progress=False)
    assert cereri[0]["encQuery"] == "70,71:72:73:74"     # everything, unfiltered

    t.matrix("AMG130A").how()
    iesire = capsys.readouterr().out
    assert "not territorial" in iesire and "get() takes everything" in iesire
    assert "m.get(level=" not in iesire


def test_how_runs_on_every_family(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    for cod in TOATE:
        t.matrix(cod).how()
        assert cod in capsys.readouterr().out
