"""Offline tests for dimension roles and for finding the fine territory.

The bug this file exists for: GOS102A calls its locality dimension 'Municipii
si orase', not 'Localitati'. The library was right, the columns came out under
that name, and downstream code matching on the literal 'Localitati_siruta'
found nothing and said nothing, so the SIRUTA and the locality name were lost
on the way to the file.

Nothing here renames a column. What is tested is that there is a way to ask
which dimension holds the fine territory, and what its columns are called,
without knowing the label INS chose.

The fixtures are real metadata, saved once: GOS102A ('Municipii si orase',
321 towns), SCL101B (counties only, no localities) and POP107D ('Localitati',
3182 of them).
"""
import json
from pathlib import Path

import pytest

import pytempo as t
from pytempo import catalog, client, endpoints, territory

from .test_smoke import FOM104D, TMP1173

FIXTURES = Path(__file__).parent / "fixtures"
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("GOS102A", "SCL101B", "POP107D")}
META["FOM104D"] = FOM104D
META["TMP1173"] = TMP1173


def _api(monkeypatch, meta=None):
    meta = meta or META
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for cod, date in meta.items():
            if url == endpoints.matrix(cod):
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


def _roles(m) -> list[tuple]:
    return [(d.label.strip(), d.role, d.finest_level) for d in m.dimensions]


# ------------------------------------------------------------------ roles

def test_roles_on_a_locality_matrix_named_localitati(monkeypatch):
    _api(monkeypatch)
    assert _roles(t.matrix("POP107D")) == [
        ("Varste si grupe de varsta", "alt", ""),
        ("Sexe", "alt", ""),
        ("Judete", "teritoriu", "judet"),
        ("Localitati", "teritoriu", "localitate"),
        ("Ani", "timp", ""),
        ("UM: Numar persoane", "um", ""),
    ]


def test_roles_on_a_locality_matrix_named_something_else(monkeypatch):
    """GOS102A: the same shape, a different word for the same thing."""
    _api(monkeypatch)
    assert _roles(t.matrix("GOS102A")) == [
        ("Judete", "teritoriu", "judet"),
        ("Municipii si orase", "teritoriu", "localitate"),
        ("Ani", "timp", ""),
        ("UM: Ha", "um", ""),
    ]


def test_roles_on_a_matrix_without_localities(monkeypatch):
    _api(monkeypatch)
    assert _roles(t.matrix("SCL101B")) == [
        ("Niveluri de educatie", "alt", ""),
        ("Medii de rezidenta", "alt", ""),
        ("Macroregiuni, regiuni de dezvoltare si judete", "teritoriu", "judet"),
        ("Ani", "timp", ""),
        ("UM: Numar", "um", ""),
    ]


def test_a_territorial_dimension_outside_the_nomenclator(monkeypatch):
    """TMP1173: monitoring stations stay territorial, but reach no real level."""
    _api(monkeypatch)
    m = t.matrix("TMP1173")
    statii = m.dimensions[1]
    assert (statii.role, statii.finest_level) == ("teritoriu", "necunoscut")
    assert m.locality_dimension is None


# ---------------------------------------------------- the canonical hook

def test_the_hook_finds_localitati(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")
    assert m.locality_dimension is m.dimensions[3]
    assert m.locality_dimension.label.strip() == "Localitati"
    assert m.territory_dimension is m.locality_dimension
    assert m.territory_columns() == {
        "label": "Localitati",
        "siruta": "Localitati_siruta",
        "nivel": "Localitati_nivel",
        "tip": "Localitati_tip",
        "nume": "Localitati_nume",
    }


def test_the_hook_finds_municipii_si_orase(monkeypatch):
    """The test the whole change exists for.

    Same question, same answer, although the dimension is called something
    that mentions neither localities nor SIRUTA.
    """
    _api(monkeypatch)
    m = t.matrix("GOS102A")
    assert m.locality_dimension is m.dimensions[1]
    assert m.locality_dimension.label.strip() == "Municipii si orase"
    assert m.territory_columns() == {
        "label": "Municipii si orase",
        "siruta": "Municipii si orase_siruta",
        "nivel": "Municipii si orase_nivel",
        "tip": "Municipii si orase_tip",
        "nume": "Municipii si orase_nume",
    }
    # and the name is untouched: nothing was renamed to make this work
    assert m.dimensions[1].label.strip() == "Municipii si orase"


def test_the_hook_is_empty_handed_without_localities(monkeypatch):
    """SCL101B reaches counties and stops there. No error, no invention."""
    _api(monkeypatch)
    m = t.matrix("SCL101B")
    assert m.locality_dimension is None
    columns = m.territory_columns()
    assert columns == {
        "label": "Macroregiuni, regiuni de dezvoltare si judete",
        "nivel": "Macroregiuni, regiuni de dezvoltare si judete_nivel",
    }
    # counties have no SIRUTA and no settlement type, so those keys are absent
    # rather than pointing at a column that will not be there
    assert "siruta" not in columns and "tip" not in columns


def test_the_hook_on_a_matrix_with_no_territory(monkeypatch):
    fara = dict(FOM104D, details={"nomJud": 0, "nomLoc": 0, "matTime": 3,
                                  "matCaen1": 0, "matCaen2": 0, "matSiruta": 0,
                                  "matRegJ": 0, "matMaxDim": 4},
                dimensionsMap=FOM104D["dimensionsMap"][2:])
    _api(monkeypatch, {"FOM104D": fara})
    m = t.matrix("FOM104D")
    assert m.locality_dimension is None
    assert m.territory_dimension is None
    assert m.territory_columns() == {}


def test_the_hook_agrees_with_the_teritoriu_shortcut(monkeypatch):
    """m.options('teritoriu') resolves to the same dimension the hook names."""
    _api(monkeypatch)
    for cod in ("GOS102A", "POP107D", "SCL101B"):
        m = t.matrix(cod)
        prin_scurtatura = m._find_dimension("teritoriu")
        assert prin_scurtatura is m.territory_dimension, cod


# ----------------------------------------- detection without any details

def _fara_details(meta: dict) -> dict:
    """The same indicator with every territorial flag cleared.

    INS does fill these in, but nothing except the flags and the label used to
    stand between the fine territory and being missed entirely. With both gone,
    only the options are left to say what the dimension holds.
    """
    return dict(meta, details=dict(meta["details"], nomJud=0, nomLoc=0,
                                   matSiruta=0, matRegJ=0))


def test_localities_are_found_from_the_options_alone(monkeypatch):
    """GOS102A with details silent: the names of the options give it away."""
    _api(monkeypatch, {"GOS102A": _fara_details(META["GOS102A"])})
    m = t.matrix("GOS102A")

    orase = m.dimensions[1]
    assert territory.is_territorial(orase, m.details) is True
    assert territory.is_locality_dimension(orase, m.details) is True
    assert m.locality_dimension is orase
    assert m.territory_columns()["siruta"] == "Municipii si orase_siruta"
    # the county dimension is still recognized, from its option names
    assert m.dimensions[0].role == "teritoriu"
    assert m.levels == ["national", "judet", "localitate"]


def test_counties_are_found_from_the_options_alone(monkeypatch):
    """SCL101B with matRegJ cleared: county names are evidence enough."""
    _api(monkeypatch, {"SCL101B": _fara_details(META["SCL101B"])})
    m = t.matrix("SCL101B")
    assert m.dimensions[2].role == "teritoriu"
    assert m.dimensions[2].finest_level == "judet"
    assert m.locality_dimension is None


def test_numbers_at_the_start_of_a_label_are_not_a_siruta_code(monkeypatch):
    """The guard on the evidence route.

    POP107D's ages read '0 ani', '1 ani', which start with a number exactly the
    way '1017 MUNICIPIUL ALBA IULIA' does. A rule that only looked for a
    numeric prefix would have turned the age dimension into a territory.
    """
    _api(monkeypatch, {"POP107D": _fara_details(META["POP107D"])})
    m = t.matrix("POP107D")
    varste = m.dimensions[0]
    assert varste.label.strip() == "Varste si grupe de varsta"
    assert territory.is_territorial(varste, m.details) is False
    assert varste.role == "alt"
    assert territory.is_locality_dimension(varste, m.details) is False


def test_a_caen_dimension_with_numeric_codes_stays_caen(monkeypatch):
    """Activity codes look numeric too, and are not places either."""
    caen = dict(FOM104D, details=dict(FOM104D["details"], nomJud=0, nomLoc=0,
                                      matSiruta=0),
                dimensionsMap=[
        {"dimCode": 1, "label": "CAEN Rev.2 (activitati)", "options": [
            {"label": "01 Agricultura", "nomItemId": 1, "offset": 1,
             "parentId": None},
            {"label": "02 Silvicultura", "nomItemId": 2, "offset": 2,
             "parentId": None},
            {"label": "10 Industria alimentara", "nomItemId": 3, "offset": 3,
             "parentId": None}]},
        FOM104D["dimensionsMap"][2],
        FOM104D["dimensionsMap"][3],
    ])
    _api(monkeypatch, {"FOM104D": caen})
    m = t.matrix("FOM104D")
    assert m.dimensions[0].role == "caen"
    assert m.territory_dimension is None


# ------------------------------------- the columns the hook promises exist

CSV_GOS102A = (
    "Judete, Municipii si orase, Ani, UM: Ha, Valoare\n"
    "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 2023, Hectare, 1240.5\n"
    "Alba, 1213 MUNICIPIUL AIUD, Anul 2023, Hectare, 830.0\n"
)


def test_the_named_columns_are_the_ones_get_produces(monkeypatch):
    """The promise checked against the data: every name the hook gives back is
    a column of the frame, spelled the same way."""
    _api(monkeypatch)
    monkeypatch.setattr(client, "post_pivot", lambda payload, **kw: CSV_GOS102A)

    m = t.matrix("GOS102A")
    # one county, so the whole indicator fits in a single request
    df = m.get(select={"Judete": ["Alba"]}, progress=False)
    for key, column in m.territory_columns().items():
        assert column in df.columns, key

    # and they carry what they say: this is what downstream maps to siruta
    coloane = m.territory_columns()
    assert df[coloane["siruta"]].tolist() == [1017, 1213]
    assert df[coloane["tip"]].tolist() == ["municipiu", "municipiu"]
    assert df[coloane["nume"]].tolist() == ["ALBA IULIA", "AIUD"]
    assert df[coloane["nivel"]].tolist() == ["localitate", "localitate"]
    # the original column keeps the INS name, prefix and all
    assert df[coloane["label"]].tolist() == [
        "1017 MUNICIPIUL ALBA IULIA", "1213 MUNICIPIUL AIUD"]


def test_downstream_can_map_without_knowing_the_label(monkeypatch):
    """The downstream shape, in three lines: no literal 'Localitati' anywhere."""
    _api(monkeypatch)
    monkeypatch.setattr(client, "post_pivot", lambda payload, **kw: CSV_GOS102A)

    m = t.matrix("GOS102A")
    coloane = m.territory_columns()
    df = m.get(select={"Judete": ["Alba"]}, progress=False).rename(columns={
        coloane["siruta"]: "siruta", coloane["nume"]: "uat_name"})

    assert df["siruta"].tolist() == [1017, 1213]
    assert df["uat_name"].tolist() == ["ALBA IULIA", "AIUD"]


# ------------------------------------------------------------ regression

CSV_FOM104D_MIC = (
    "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
    "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 1990, Numar persoane, 31.5\n"
)


def test_get_columns_are_exactly_what_they_were(monkeypatch):
    """Nothing was renamed, nothing was added to the output frame."""
    _api(monkeypatch)
    monkeypatch.setattr(client, "post_pivot",
                        lambda payload, **kw: CSV_FOM104D_MIC)

    df = t.matrix("FOM104D").get(level="localitate", progress=False)
    assert list(df.columns) == [
        "Judete", "Localitati", "Ani", "UM: Numar persoane", "Valoare",
        "Judete_nivel",
        "Localitati_siruta", "Localitati_nivel", "Localitati_tip",
        "Localitati_nume", "Ani_an"]


def test_levels_and_plans_are_unchanged(monkeypatch):
    _api(monkeypatch)
    assert t.matrix("POP107D").levels == ["national", "judet", "localitate"]
    assert t.matrix("SCL101B").levels == [
        "national", "macroregiune", "regiune", "judet"]
    assert t.matrix("GOS102A").levels == ["national", "judet", "localitate"]


def test_the_hook_needs_no_second_request(monkeypatch):
    """Asking is metadata work, not network work."""
    _api(monkeypatch)
    m = t.matrix("GOS102A")
    monkeypatch.setattr(client, "get_json", lambda *a, **kw: pytest.fail(
        "territory_columns() should not fetch anything"))
    assert m.territory_columns()["label"] == "Municipii si orase"
