"""Teste offline pentru get-ul ca executor de plan si trio-ul what/where/how."""
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

# indicator fara nicio dimensiune teritoriala
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

    # planul spune judet, deci se cer doar judetele
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"
    iesire = capsys.readouterr().out
    assert "nivel judet (cel mai fin)" in iesire
    # tidy e implicit acum
    assert any(c.endswith("_nivel") for c in df.columns)


def test_get_raw_gives_untouched_columns(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    _post(monkeypatch, CSV)
    m = t.matrix("SOM101B")
    brut = m.get(raw=True, progress=False)
    curat = m.get(progress=False)
    assert brut.shape[1] < curat.shape[1]
    assert not any(c.endswith("_nivel") for c in brut.columns)
    # tidy=False face acelasi lucru
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
    """Calea implicita pe judet plus localitate merge, prin by_county."""
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    cereri = _post(monkeypatch, CSV)

    df = t.matrix("FOM104D").get(progress=False)
    assert len(cereri) == 3            # cate un judet fiecare
    assert len(df) == 6
    assert "Localitati_siruta" in df.columns


def test_get_neteritorial_has_no_territorial_filter(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    csv_tmp = ("Categorii de emisii, Statii de monitorizare de tip fond urban "
               "- Localitate, Ani, Unitati de masura, Valoare\n"
               "Total, BT-1 - Municipiul Botosani, Anul 2024, Micrograme, 26.2\n")
    cereri = _post(monkeypatch, {"TMP1173": csv_tmp})
    t.matrix("TMP1173").get(progress=False)
    # planul nu are default_level util, deci se cer toate optiunile
    assert cereri[0]["encQuery"].split(":")[1] == "61,62,63"


def test_get_asks_before_expensive_download(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path, dict(TOATE, FOM104D=FOM104D_MIC))
    monkeypatch.setattr(chunking, "MAX_CELLS", 2)
    # pytempo.matrix e functia; modulul se ia din sys.modules
    monkeypatch.setattr(sys.modules["pytempo.matrix"], "POLITE_REQUESTS", 2)
    cereri = _post(monkeypatch, CSV)

    monkeypatch.setattr("builtins.input", lambda _: "n")
    try:
        t.matrix("FOM104D").get(progress=False)
    except ValueError as e:
        assert "anulata" in str(e)
    else:
        raise AssertionError("trebuia sa ceara confirmare si sa se opreasca")
    assert cereri == []

    # confirm=False taie intrebarea, pentru scripturi
    t.matrix("FOM104D").get(progress=False, confirm=False)
    assert len(cereri) > 2


def test_get_falls_back_without_registry(monkeypatch, tmp_path):
    _api(monkeypatch)
    monkeypatch.setattr(schemas.build, "REGISTRY_PATH",
                        tmp_path / "nu_exista.json")
    cereri = _post(monkeypatch, CSV)
    t.matrix("SOM101B").get(progress=False)
    # planul se calculeaza la runtime, deci tot judetele ies
    assert cereri[0]["encQuery"].split(":")[0] == "4,5"


def test_progress_auto_is_quiet_for_one_request(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    _post(monkeypatch, CSV)
    t.matrix("SOM101B").get()
    iesire = capsys.readouterr().out
    assert "1 cerere" in iesire
    assert "1/1" not in iesire       # fara progres per cerere


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
    assert "1990" in iesire and "rupturi de serie" in iesire


def test_where_shows_coverage(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    t.matrix("SOM101B").where()
    iesire = capsys.readouterr().out
    assert "domeniu" in iesire
    assert "teritoriu" in iesire
    assert "judet" in iesire
    assert "SIRUTA" in iesire
    assert "timp" in iesire and "2020" in iesire


def test_where_says_when_not_territorial(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    fara = t.matrix("FOM101A")
    # ii scoatem dimensiunea teritoriala, ca sa ramana una neteritoriala
    fara.dimensions = [d for d in fara.dimensions if d.role != "teritoriu"]
    fara.where()
    assert "nu e teritorial" in capsys.readouterr().out


def test_how_lists_only_its_own_levels(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    t.matrix("SOM101B").how()
    iesire = capsys.readouterr().out
    assert "m.get()" in iesire
    for nivel in ("national", "macroregiune", "regiune", "judet"):
        assert nivel in iesire
    # SOM101B nu coboara la localitate, deci nu il propunem
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
    assert "530" in iesire and "ATENTIE" in iesire
    assert "confirm=False" in iesire


def test_how_does_not_offer_a_level_that_would_raise(monkeypatch, tmp_path,
                                                     capsys):
    """FOM104D are judet si localitate separate: get(level=...) ar arunca."""
    _registry(monkeypatch, tmp_path)
    t.matrix("FOM104D").how()
    iesire = capsys.readouterr().out
    assert "m.get(level=" not in iesire
    assert "dimensiuni separate" in iesire


def test_unknown_only_levels_mean_no_territorial_filter(monkeypatch, tmp_path):
    """TMP1173: nivelele sunt doar 'necunoscut', deci get() ia tot."""
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
    """Un nivel real bate 'necunoscut' la alegerea celui mai fin."""
    plan = schemas.plan_for({
        "dims": [{"label": "Judete", "role": "teritoriu", "n_options": 50}],
        "levels": ["national", "macroregiune", "regiune", "judet",
                   "necunoscut"],
        "total_cells": 50, "family": "teritorial_simplu"})
    assert plan["default_level"] == "judet"


def test_how_explains_when_level_filter_does_not_apply(monkeypatch, tmp_path,
                                                       capsys):
    _registry(monkeypatch, tmp_path)
    # doar 'necunoscut': denumirile nu se incadreaza in nomenclator
    t.matrix("TMP1173").how()
    iesire = capsys.readouterr().out
    assert "nu se aplica aici" in iesire and "get() ia tot" in iesire
    assert "m.get(level=" not in iesire


def test_non_territorial_get_and_how(monkeypatch, tmp_path, capsys):
    """Neteritorialul nu are ce filtra: get() ia tot, how() o spune."""
    _registry(monkeypatch, tmp_path, dict(TOATE, AMG130A=NETERITORIAL))
    fisa = schemas.load_registry(schemas.build.REGISTRY_PATH)["entries"]
    assert fisa["AMG130A"]["levels"] == []
    assert fisa["AMG130A"]["fetch_plan"]["default_level"] is None

    csv = ("Grupe de varsta, Sexe, Perioade, UM: Numar persoane, Valoare\n"
           "Total, Total, Anul 2024, Numar persoane, 100.0\n")
    cereri = _post(monkeypatch, {"AMG130A": csv})
    t.matrix("AMG130A").get(progress=False)
    assert cereri[0]["encQuery"] == "70,71:72:73:74"     # tot, nefiltrat

    t.matrix("AMG130A").how()
    iesire = capsys.readouterr().out
    assert "nu e teritorial" in iesire and "get() ia tot" in iesire
    assert "m.get(level=" not in iesire


def test_how_runs_on_every_family(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    for cod in TOATE:
        t.matrix(cod).how()
        assert cod in capsys.readouterr().out
