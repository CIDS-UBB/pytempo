"""Offline tests for validation and fetch plans. No network."""
import json
import sys

import pytempo as t
import pytempo.schemas.validate  # noqa: F401  (ca sa intre in sys.modules)
from pytempo import catalog, client, endpoints, schemas

# schemas.validate is the function; the module comes from sys.modules
v = sys.modules["pytempo.schemas.validate"]

from .test_smoke import FOM101A, FOM104D, FOM104F, SOM101B

TOATE = {"FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A,
         "FOM104F": FOM104F}


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


# fixture CSVs, with the header exactly as INS returns it
CSV = {
    "FOM104D": ("Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
                "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 1990, Numar persoane, 31.5\n"
                "Alba, 1026 ORAS ABRUD, Anul 1990, Numar persoane, 12.0\n"),
    "SOM101B": ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                "UM: Numar persoane, Valoare\n"
                "TOTAL, Anul 2020, Numar persoane, 100.0\n"
                "Bihor, Anul 2020, Numar persoane, 12.5\n"),
    "FOM101A": ("Sexe, Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                "UM: Mii persoane, Valoare\n"
                "Total, TOTAL, Anul 2020, Mii persoane, 500.0\n"
                "Total, Cluj, Anul 2020, Mii persoane, 40.0\n"),
    "FOM104F": ("CAEN Rev.2  (activitati ale economiei nationale), Sexe, "
                "Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                "UM: Numar persoane, Valoare\n"
                "TOTAL, Total, TOTAL, Anul 2024, Numar persoane, 9.0\n"
                "TOTAL, Total, Bihor, Anul 2024, Numar persoane, 3.0\n"),
}


def _post(monkeypatch, raspunsuri=None, punctual=None):
    """Mock the POST: the first request gives the slice, the second the point
    cell."""
    raspunsuri = raspunsuri or CSV
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        cod = payload["matCode"]
        felie = raspunsuri[cod]
        # a request with one option per dimension is the point cell
        e_punctuala = all("," not in bloc
                          for bloc in payload["encQuery"].split(":"))
        if e_punctuala and punctual is not None and cod in punctual:
            return punctual[cod]
        if e_punctuala:
            antet, *randuri = felie.strip().split("\n")
            mijloc = randuri[len(randuri) // 2]
            return f"{antet}\n{mijloc}\n"
        return felie

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return cereri


# ------------------------------------------------------------ stratificare

def test_stratified_sample_respects_minimum_per_family():
    entries = {}
    for i in range(1000):
        entries[f"N{i}"] = {"status": "ok", "family": "neteritorial"}
    for i in range(5):
        entries[f"L{i}"] = {"status": "ok", "family": "judet_localitate"}
    for i in range(4):
        entries[f"C{i}"] = {"status": "ok", "family": "teritorial_caen"}

    ales = v.stratified_sample(entries, 20, seed=1)
    familii = {}
    for cod in ales:
        familii[entries[cod]["family"]] = familii.get(
            entries[cod]["family"], 0) + 1

    assert familii["judet_localitate"] >= v.MIN_PER_FAMILY
    assert familii["teritorial_caen"] >= v.MIN_PER_FAMILY
    # the non territorial family is the largest, so it takes far more than the floor
    assert familii["neteritorial"] > v.MIN_PER_FAMILY
    # fixed seed: the same sample
    assert v.stratified_sample(entries, 20, seed=1) == ales
    assert v.stratified_sample(entries, 20, seed=2) != ales


def test_stratified_sample_skips_non_ok():
    entries = {"A": {"status": "ok", "family": "neteritorial"},
               "B": {"status": "error: mort", "family": "alt"}}
    assert v.stratified_sample(entries, 5, seed=0) == ["A"]


# ------------------------------------------------------------------- felia

def test_slice_neteritorial_uses_one_year_only(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    m = t.matrix("FOM101A")
    e = schemas.load_registry()["entries"]["FOM101A"]
    selectie = v._slice_for(m, e)
    # Sexe: first option; territory: all; Ani: a single year; UM: first
    assert len(selectie[0]) == 1
    assert len(selectie[2]) == 1
    assert len(selectie[3]) == 1


def test_slice_judet_localitate_takes_one_county(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    m = t.matrix("FOM104D")
    e = schemas.load_registry()["entries"]["FOM104D"]
    selectie = v._slice_for(m, e)
    # the chosen county is Alba (the first that is not TOTAL), with its localities
    assert selectie[0] == [3064]
    assert sorted(selectie[1]) == [113, 114]
    assert len(selectie[2]) == 1          # a single year


def test_slice_is_small(monkeypatch, tmp_path):
    _registry(monkeypatch, tmp_path)
    from pytempo import chunking
    for cod in TOATE:
        m = t.matrix(cod)
        e = schemas.load_registry()["entries"][cod]
        assert chunking.cells(v._slice_for(m, e)) <= 500, cod


# --------------------------------------------------------------- validate

def test_validate_writes_status(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    date = v.validate(progress=False, delay=0, path=cale)

    for cod in TOATE:
        e = date["entries"][cod]
        assert e["validation"] == "ok", (cod, e["validation"])
        assert e["validated_at"]
        assert e["validated_version"] == schemas.REGISTRY_VERSION
        assert e["slice_cells"] > 0
    assert json.loads(cale.read_text(encoding="utf-8")) == date


def test_validate_resume_skips_done(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    cereri = _post(monkeypatch)
    v.validate(progress=False, delay=0, path=cale)
    nr = len(cereri)
    assert nr > 0

    cereri.clear()
    v.validate(progress=False, delay=0, path=cale)
    assert cereri == []                       # everything was already ok

    cereri.clear()
    v.validate(progress=False, delay=0, resume=False, path=cale)
    assert len(cereri) == nr


def test_validate_point_cell_mismatch_is_error(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    # the second request returns a different value than the slice
    stricat = {
        "SOM101B": ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                    "UM: Numar persoane, Valoare\n"
                    "Bihor, Anul 2020, Numar persoane, 999.0\n"),
    }
    _post(monkeypatch, punctual=stricat)
    date = v.validate(sample=None, progress=False, delay=0, path=cale)
    assert date["entries"]["SOM101B"]["validation"].startswith("error:")
    assert "point cell differs" in date["entries"]["SOM101B"]["validation"]
    # the others are unaffected
    assert date["entries"]["FOM104D"]["validation"] == "ok"


def test_validate_empty_is_not_an_error(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    gol = dict(CSV)
    gol["SOM101B"] = ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                      "UM: Numar persoane, Valoare\n")
    _post(monkeypatch, raspunsuri=gol)
    date = v.validate(progress=False, delay=0, path=cale)
    assert date["entries"]["SOM101B"]["validation"] == "empty"


def test_negatives_allowed_for_balance_indicators(monkeypatch, tmp_path):
    """A 'spor' or 'sold' indicator legitimately goes negative."""
    sold = dict(SOM101B,
                matrixName="Sporul natural al populatiei pe judete")
    cale = _registry(monkeypatch, tmp_path, dict(TOATE, SOM101B=sold))
    negativ = dict(CSV)
    negativ["SOM101B"] = ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                          "UM: Numar persoane, Valoare\n"
                          "Bihor, Anul 2020, Numar persoane, -576.0\n")
    _post(monkeypatch, raspunsuri=negativ)
    date = v.validate(progress=False, delay=0, path=cale)
    assert date["entries"]["SOM101B"]["validation"] == "ok"


def test_balance_word_can_come_from_a_dimension_label(monkeypatch, tmp_path):
    cu_dim = dict(SOM101B, dimensionsMap=[
        dict(SOM101B["dimensionsMap"][0], label="Soldul migratoriu pe judete"),
        SOM101B["dimensionsMap"][1], SOM101B["dimensionsMap"][2]])
    cale = _registry(monkeypatch, tmp_path, dict(TOATE, SOM101B=cu_dim))
    negativ = dict(CSV)
    negativ["SOM101B"] = ("Soldul migratoriu pe judete, Ani, "
                          "UM: Numar persoane, Valoare\n"
                          "Bihor, Anul 2020, Numar persoane, -12.0\n")
    _post(monkeypatch, raspunsuri=negativ)
    date = v.validate(progress=False, delay=0, path=cale)
    assert date["entries"]["SOM101B"]["validation"] == "ok"


def test_validate_negative_persons_is_an_error(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    negativ = dict(CSV)
    negativ["SOM101B"] = ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                          "UM: Numar persoane, Valoare\n"
                          "Bihor, Anul 2020, Numar persoane, -5.0\n")
    _post(monkeypatch, raspunsuri=negativ)
    date = v.validate(progress=False, delay=0, path=cale)
    assert "negative" in date["entries"]["SOM101B"]["validation"]


def test_unparsable_csv_is_needs_review_not_error(monkeypatch, tmp_path):
    """A broken CSV is about what INS sent, so it goes to a human."""
    cale = _registry(monkeypatch, tmp_path)
    stricat = dict(CSV)
    # a value column carrying the INS confidentiality marker
    stricat["SOM101B"] = ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                          "UM: Numar persoane, Valoare\n"
                          "Bihor, Anul 2020, Numar persoane, c\n")
    _post(monkeypatch, raspunsuri=stricat)
    date = v.validate(progress=False, delay=0, path=cale)

    starea = date["entries"]["SOM101B"]["validation"]
    assert starea.startswith("needs_review:")
    assert "non numeric markers" in starea and "'c'" in starea
    assert "not numeric" in starea          # the parse error is kept too
    assert date["entries"]["SOM101B"]["slice_cells"] > 0
    # the others are unaffected
    assert date["entries"]["FOM104D"]["validation"] == "ok"


def test_needs_review_is_listed_apart_in_the_report(monkeypatch, tmp_path,
                                                    capsys):
    cale = _registry(monkeypatch, tmp_path)
    date = schemas.load_registry(cale)
    date["entries"]["SOM101B"]["validation"] = "needs_review: odd header"
    date["entries"]["FOM104D"]["validation"] = "error: something real"
    v._save(date, cale)

    v.validation_report(path=cale)
    iesire = capsys.readouterr().out
    assert "needs review : 1" in iesire
    assert "documented exceptions" in iesire
    assert "errors       : 1" in iesire
    assert "odd header" in iesire


def test_targeted_mode_validates_only_the_given_codes(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    cereri = _post(monkeypatch)
    date = v.validate(codes=["SOM101B"], progress=False, delay=0, path=cale)

    assert date["entries"]["SOM101B"]["validation"] == "ok"
    assert "validation" not in date["entries"]["FOM104D"]
    assert {p["matCode"] for p in cereri} == {"SOM101B"}


def test_audit_standardization_reports_by_kind(monkeypatch, tmp_path, capsys):
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    gasite = v.audit_standardization(delay=0, progress=False, path=cale)

    assert set(gasite) == {"empty_derived", "all_unknown", "nothing_added"}
    iesire = capsys.readouterr().out
    assert "Standardization audit" in iesire
    for tip in gasite:
        assert tip in iesire
    # nothing in these fixtures produces an empty derived column any more
    assert gasite["empty_derived"] == []


def test_audit_standardization_flags_all_unknown_levels(monkeypatch, tmp_path,
                                                        capsys):
    """A dimension whose names are not administrative units gets flagged."""
    from .test_smoke import TMP1173
    cale = _registry(monkeypatch, tmp_path, dict(TOATE, TMP1173=TMP1173))
    csv_tmp = ("Categorii de emisii, Statii de monitorizare de tip fond urban "
               "- Localitate, Ani, Unitati de masura, Valoare\n"
               "Total, BT-1 - Municipiul Botosani, Anul 2024, Micrograme, 26.2\n")
    _post(monkeypatch, raspunsuri=dict(CSV, TMP1173=csv_tmp))
    gasite = v.audit_standardization(delay=0, progress=False, path=cale)
    assert "TMP1173" in gasite["all_unknown"]


def test_targeted_mode_rejects_unknown_codes(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    try:
        v.validate(codes=["NU_EXISTA"], progress=False, delay=0, path=cale)
    except ValueError as e:
        assert "NU_EXISTA" in str(e)
    else:
        raise AssertionError("an unknown code should raise")


def test_validation_report_names_locality_without_siruta(monkeypatch, tmp_path,
                                                         capsys):
    cale = _registry(monkeypatch, tmp_path)
    date = schemas.load_registry(cale)
    date["entries"]["FOM104D"]["has_siruta"] = False   # simulating TMP1173
    v._save(date, cale)

    v.validation_report(path=cale)
    iesire = capsys.readouterr().out
    assert "localities without SIRUTA" in iesire
    assert "FOM104D" in iesire


# --------------------------------------------------------- spot_check_list

def test_spot_check_list_returns_rows_with_url(monkeypatch, tmp_path, capsys):
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    v.validate(progress=False, delay=0, path=cale)
    capsys.readouterr()

    randuri = v.spot_check_list(3, seed=7, path=cale)
    assert len(randuri) == 3
    for r in randuri:
        assert r["url"].endswith(f"matrix/{r['code']}")
        assert r["combination"]
        assert r["value"] is not None
    iesire = capsys.readouterr().out
    assert "OUR VALUE" in iesire
    assert "tempo-ins/matrix/" in iesire


# ------------------------------------------------------------- fetch_plan

def test_plan_single_under_threshold():
    plan = schemas.plan_for({"dims": [{"label": "Ani", "role": "timp",
                                       "n_options": 10}],
                             "levels": [], "total_cells": 10,
                             "family": "neteritorial"})
    assert plan["strategy"] == "single"
    assert plan["est_requests"] == 1
    assert plan["default_level"] is None
    assert plan["tidy_ready"] is True


def test_plan_by_county_for_localities():
    plan = schemas.plan_for({
        "dims": [{"label": "Judete", "role": "teritoriu", "n_options": 43},
                 {"label": "Localitati", "role": "teritoriu",
                  "n_options": 3183},
                 {"label": "Ani", "role": "timp", "n_options": 35}],
        "levels": ["national", "judet", "localitate"],
        "total_cells": 43 * 3183 * 35,
        "family": "judet_localitate"})
    assert plan["strategy"] == "by_county"
    assert plan["est_requests"] == 43
    assert plan["default_level"] == "localitate"


def test_plan_split_for_big_without_localities():
    """Those over the threshold without localities get split, not an error."""
    plan = schemas.plan_for({
        "dims": [{"label": "Macroregiuni, regiuni si judete",
                  "role": "teritoriu", "n_options": 56},
                 {"label": "Categorii", "role": "alt", "n_options": 900},
                 {"label": "Ani", "role": "timp", "n_options": 35}],
        "levels": ["national", "judet"],
        "total_cells": 56 * 900 * 35,
        "family": "teritorial_simplu"})
    assert plan["strategy"] == "split:Categorii"
    assert plan["est_requests"] > 1
    assert plan["default_level"] == "judet"


def test_plan_split_when_localities_have_no_county_dim():
    """A single territorial dimension, like TMP1173: split, not by_county."""
    plan = schemas.plan_for({
        "dims": [{"label": "Statii de monitorizare", "role": "teritoriu",
                  "n_options": 121},
                 {"label": "Ani", "role": "timp", "n_options": 17},
                 {"label": "Categorii", "role": "alt", "n_options": 200}],
        "levels": ["localitate"],
        "total_cells": 121 * 17 * 200,
        "family": "judet_localitate"})
    assert plan["strategy"].startswith("split:")
    assert plan["default_level"] == "localitate"


def test_plan_tidy_ready_false_without_territory_or_time():
    plan = schemas.plan_for({"dims": [{"label": "Sexe", "role": "alt",
                                       "n_options": 3}],
                             "levels": [], "total_cells": 3,
                             "family": "neteritorial"})
    assert plan["tidy_ready"] is False


def test_refresh_plans_writes_every_entry(monkeypatch, tmp_path, capsys):
    cale = _registry(monkeypatch, tmp_path)
    date = schemas.load_registry(cale)
    for e in date["entries"].values():
        e.pop("fetch_plan", None)
    v._save(date, cale)

    date = schemas.refresh_plans(path=cale, progress=False)
    for cod, e in date["entries"].items():
        assert "fetch_plan" in e, cod
        assert e["fetch_plan"]["strategy"]
    assert date["entries"]["FOM104D"]["fetch_plan"]["default_level"] == \
        "localitate"


def test_rebuild_keeps_validation(monkeypatch, tmp_path):
    """A rebuild does not throw the validation away if the indicator is the same."""
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    v.validate(progress=False, delay=0, path=cale)

    schemas.build_registry(confirm=False, progress=False, incremental=False,
                           path=cale)
    e = schemas.load_registry(cale)["entries"]["FOM104D"]
    assert e["validation"] == "ok"
    assert e["validated_at"]
    assert e["slice_cells"] > 0


def test_rebuild_drops_validation_when_indicator_changed(monkeypatch, tmp_path):
    """If INS updated the indicator, the old validation no longer counts."""
    cale = _registry(monkeypatch, tmp_path)
    _post(monkeypatch)
    v.validate(progress=False, delay=0, path=cale)

    _api(monkeypatch, dict(TOATE, FOM104D=dict(
        FOM104D, ultimaActualizare="01-01-2099")))
    schemas.build_registry(confirm=False, progress=False, incremental=False,
                           path=cale)
    e = schemas.load_registry(cale)["entries"]["FOM104D"]
    assert "validation" not in e
    # ceilalti isi pastreaza validarea
    assert schemas.load_registry(cale)["entries"]["SOM101B"]["validation"] == "ok"


def test_build_registry_includes_plan(monkeypatch, tmp_path):
    cale = _registry(monkeypatch, tmp_path)
    date = schemas.load_registry(cale)
    assert date["entries"]["SOM101B"]["fetch_plan"]["strategy"] == "single"
    assert date["entries"]["SOM101B"]["fetch_plan"]["default_level"] == "judet"
