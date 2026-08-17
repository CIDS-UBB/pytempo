"""Offline tests for df.tempo.spot_check, the manual verification helper.

It prepares a comparison against TEMPO Online and does nothing else: no
request, no derived truth, just a unit picked at random, every other dimension
pinned, and the series printed the way it will be read off the screen.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

import pytempo as t
from pytempo import catalog, client, endpoints, parse

from .test_smoke import FOM104D_MIC

FIXTURES = Path(__file__).parent / "fixtures"
POP107D = json.loads((FIXTURES / "POP107D_meta.json").read_text(
    encoding="utf-8"))
META = {"POP107D": POP107D, "FOM104D": FOM104D_MIC}


def _api(monkeypatch, meta=META):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for cod, date in meta.items():
            if url == endpoints.matrix(cod):
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


def _tidy(m, rows) -> pd.DataFrame:
    """A tidy frame, standardized the way get() standardizes it."""
    columns = [d.label.strip() for d in m.dimensions] + ["Valoare"]
    return parse.standardize(pd.DataFrame(rows, columns=columns), m)


LOCALITATI = ("1017 MUNICIPIUL ALBA IULIA", "2130 ALBAC",
              "3000 MUNICIPIUL ARAD")


def _fom104d(monkeypatch) -> pd.DataFrame:
    """Territory, year and value only: no inner dimension to pin."""
    _api(monkeypatch)
    m = t.matrix("FOM104D")
    rows = [["Alba" if loc != LOCALITATI[2] else "Arad", loc, an,
             "Numar persoane", value]
            for loc in LOCALITATI
            for an, value in (("Anul 2023", 10.0), ("Anul 2024", 0.0))]
    return _tidy(m, rows)


def _pop107d(monkeypatch, sexes=("Total", "Masculin")) -> pd.DataFrame:
    """The same, with an inner dimension: sex, with or without its total."""
    _api(monkeypatch)
    m = t.matrix("POP107D")
    rows = [["Total", sex, "Alba", loc, an, "Numar persoane", value]
            for loc in LOCALITATI[:2]
            for sex in sexes
            for an, value in (("Anul 2020", 100.0), ("Anul 2021", 0.0))]
    return _tidy(m, rows)


# ------------------------------------------------------- the simple frame

def test_spot_check_prints_a_unit_and_its_series(monkeypatch, capsys):
    df = _fom104d(monkeypatch)
    df.tempo.spot_check(seed=1)
    out = capsys.readouterr().out

    assert "spot check: 1 of 3 units, seed 1" in out
    # the unit is named the way INS names it, county and SIRUTA alongside
    assert "[Judete: " in out
    assert "siruta " in out
    # the series, year by year, including a real zero
    assert "2 years:" in out
    assert "2023  10.0" in out
    assert "2024  0.0" in out
    # and where to go with it
    assert endpoints.site() in out
    assert "a year missing here is a ':' on the site, not a zero" in out


def test_the_seed_makes_the_choice_reproducible(monkeypatch, capsys):
    df = _fom104d(monkeypatch)
    df.tempo.spot_check(seed=3)
    first = capsys.readouterr().out
    df.tempo.spot_check(seed=3)
    assert capsys.readouterr().out == first


def test_different_seeds_reach_different_units(monkeypatch, capsys):
    """Random means random: the seed pins it, it does not narrow it."""
    df = _fom104d(monkeypatch)
    chosen = set()
    for seed in range(20):
        df.tempo.spot_check(seed=seed)
        out = capsys.readouterr().out
        chosen |= {loc for loc in LOCALITATI if loc in out}
    assert chosen == set(LOCALITATI)


def test_n_picks_several_distinct_units(monkeypatch, capsys):
    df = _fom104d(monkeypatch)
    df.tempo.spot_check(n=3, seed=5)
    out = capsys.readouterr().out
    assert "spot check: 3 of 3 units" in out
    for loc in LOCALITATI:
        assert loc in out
    assert out.count("years:") == 3


def test_asking_for_more_units_than_there_are(monkeypatch, capsys):
    df = _fom104d(monkeypatch)
    df.tempo.spot_check(n=10, seed=5)
    assert "spot check: 3 of 3 units" in capsys.readouterr().out


# ------------------------------------------------- pinning inner dimensions

def test_an_inner_dimension_is_pinned_on_its_total(monkeypatch, capsys):
    """One series, not three, so the site shows one line to compare."""
    df = _pop107d(monkeypatch)
    df.tempo.spot_check(seed=1)
    out = capsys.readouterr().out

    assert "fixed Sexe = Total" in out
    assert "fixed Varste si grupe de varsta = Total" in out
    assert "no total among" not in out
    # pinned down to a single series: one row per year, and 'Masculin' left out
    assert "2 years:" in out
    assert "2020  100.0" in out
    assert "more rows than years" not in out


def test_a_dimension_without_a_total_is_pinned_and_announced(monkeypatch,
                                                             capsys):
    """Silence here would compare two different things without saying so."""
    df = _pop107d(monkeypatch, sexes=("Masculin", "Feminin"))
    df.tempo.spot_check(seed=1)
    out = capsys.readouterr().out

    assert "fixed Sexe = Masculin   (no total among its 2 values)" in out
    assert "2 years:" in out
    assert "more rows than years" not in out


def test_the_unit_of_measure_is_not_pinned_when_it_never_varies(monkeypatch,
                                                                capsys):
    df = _pop107d(monkeypatch)
    df.tempo.spot_check(seed=1)
    assert "fixed UM:" not in capsys.readouterr().out


def test_only_units_that_carry_a_value_are_offered(monkeypatch, capsys):
    """A unit whose every row is empty is nothing to check by hand."""
    df = _fom104d(monkeypatch)
    df.loc[df["Localitati"] == "2130 ALBAC", "Valoare"] = None

    for seed in range(20):
        df.tempo.spot_check(seed=seed)
        out = capsys.readouterr().out
        assert "2130 ALBAC" not in out
    assert "spot check: 1 of 3 units" in out


# ------------------------------------------------------------ no network

def test_spot_check_touches_no_network(monkeypatch, capsys):
    """It reads the frame that is already downloaded, and only that."""
    df = _pop107d(monkeypatch)

    def refuse(*a, **kw):
        raise AssertionError("spot_check must not call the API")

    monkeypatch.setattr(client, "post_pivot", refuse)
    monkeypatch.setattr(client, "get_json", refuse)
    monkeypatch.setattr(client, "url_ok", refuse)

    df.tempo.spot_check(n=2, seed=2)
    assert "spot check: 2 of 2 units" in capsys.readouterr().out


# --------------------------------------------------------- what it refuses

def test_spot_check_on_a_frame_that_is_not_tidy_output():
    plain = pd.DataFrame({"a": [1], "Valoare": [2.0]})
    with pytest.raises(ValueError) as info:
        plain.tempo.spot_check()
    assert "does not look like pytempo tidy output" in str(info.value)


def test_spot_check_without_a_territorial_dimension(monkeypatch):
    """A non territorial indicator has no unit to look up."""
    df = _pop107d(monkeypatch)
    fara = df.drop(columns=[c for c in df.columns
                            if c.startswith(("Judete", "Localitati"))])
    with pytest.raises(ValueError) as info:
        fara.tempo.spot_check()
    assert "no territorial dimension" in str(info.value)


def test_spot_check_on_a_frame_with_no_values(monkeypatch):
    df = _fom104d(monkeypatch)
    df["Valoare"] = None
    with pytest.raises(ValueError) as info:
        df.tempo.spot_check()
    assert "nothing to check by hand" in str(info.value)
