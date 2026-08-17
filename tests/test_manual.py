"""Offline tests for how() as the menu of one indicator.

how() said how to download an indicator. What it could not say is what there is
to choose, which is the part a reader does not know: that POP107D has 104 ages
in 19 groups, that its territory reaches 3181 localities, that Sexe has three
options. Without that, level= and select= are arguments you can only use once
you already know the answer.

Every number below is checked against the fixture it came from, because a menu
that prints a plausible number is worse than one that prints none.
"""
import json
from pathlib import Path

import pytempo as t
from pytempo import catalog, client, endpoints, hierarchy, manual, territory

from .test_guidance import _registry
from .test_smoke import FOM104D_MIC

FIXTURES = Path(__file__).parent / "fixtures"
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("POP107D", "FOM104F", "GOS102A")}

VARSTA = "Varste si grupe de varsta"
CAEN = "CAEN Rev.2  (activitati ale economiei nationale)"


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


def _how(monkeypatch, cod, capsys, meta=None) -> str:
    _api(monkeypatch, meta)
    t.matrix(cod).how()
    return capsys.readouterr().out


# ------------------------------------------------------- territorial level

def test_the_levels_are_listed_with_their_real_sizes(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys)

    assert "TERRITORIAL LEVEL, what level= takes here:" in out
    # the counts come from the options, and the fixture says so
    _api(monkeypatch)
    m = t.matrix("POP107D")
    counts = manual.units_per_level(m)
    assert counts == {"national": 1, "judet": 42, "localitate": 3181}

    assert "national          1 unit" in out
    assert "judet           42 units" in out
    assert "localitate    3181 units" in out
    # and the call for each one, ready to copy
    assert "m.get(level='national')" in out
    assert "m.get(level='judet')" in out
    assert "m.get(level=None)" in out


def test_each_level_says_what_it_costs(monkeypatch, capsys):
    """The useful part: which level is one request and which is hundreds."""
    out = _how(monkeypatch, "POP107D", capsys)
    _api(monkeypatch)
    m = t.matrix("POP107D")

    assert m._requests_for(["judet"]) == 5
    assert m._requests_for(["localitate"]) == 379
    assert "5 requests   m.get(level='judet')" in out
    # and the expensive one is offered through download(), not through get()
    assert ("379 requests   m.download(level='localitate', "
            "folder='data/pop107d')") in out
    assert "the finest, and the default" in out


def test_a_level_that_fits_is_offered_through_get(monkeypatch, capsys):
    """GOS102A reaches localities in 42 requests, which get() will run."""
    out = _how(monkeypatch, "GOS102A", capsys)
    assert "m.get(level='localitate')" in out
    assert "m.download(level='localitate'" not in out


def test_no_level_table_when_there_is_no_usable_level(monkeypatch, tmp_path,
                                                      capsys):
    """TMP1173's territorial names are monitoring stations, not places."""
    _registry(monkeypatch, tmp_path)
    t.matrix("TMP1173").how()
    out = capsys.readouterr().out
    assert "TERRITORIAL LEVEL" not in out
    assert "does not apply here" in out
    assert "m.get(level=" not in out


# ------------------------------------------------------------- the filters

def test_a_hierarchical_dimension_shows_its_keywords_and_counts(monkeypatch,
                                                                 capsys):
    out = _how(monkeypatch, "POP107D", capsys)
    _api(monkeypatch)
    varsta = t.matrix("POP107D")._find_dimension(VARSTA)

    # the numbers printed are the numbers the keywords really keep
    assert len(hierarchy.pick(varsta, "total")) == 1
    assert len(hierarchy.pick(varsta, "groups")) == 19
    assert len(hierarchy.pick(varsta, "leaves")) == 85

    assert f"{VARSTA}, hierarchical, 104 options" in out
    assert f"select={{{VARSTA!r}: 'total'}}" in out and "1 option" in out
    assert f"select={{{VARSTA!r}: 'groups'}}" in out and "19 options" in out
    assert f"select={{{VARSTA!r}: 'leaves'}}" in out and "85 options" in out
    assert f"m.options({VARSTA!r}, kind='groups') lists them" in out
    # the 104 options themselves stay in m.options, not in the manual
    assert "0- 4 ani" not in out


def test_a_small_flat_dimension_shows_its_values(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys)
    assert "Sexe, flat, 3 options: Total, Masculin, Feminin" in out
    # the example picks a real value, and not the total, which filters nothing
    assert "select={'Sexe': ['Masculin']}" in out


def test_a_large_flat_dimension_sends_you_to_options(monkeypatch, capsys):
    """FOM104F's CAEN has 68 options and no levels: listing them helps nobody."""
    out = _how(monkeypatch, "FOM104F", capsys)

    assert f"{CAEN}, flat, 68 options, too many to list here" in out
    assert f"m.options({CAEN!r}) shows them" in out
    # not a keyword, since there is no hierarchy to read
    assert f"select={{{CAEN!r}: 'groups'}}" not in out


def test_an_indicator_with_nothing_to_filter_says_so(monkeypatch, capsys):
    """GOS102A is county, town and year. There is no third thing to choose."""
    out = _how(monkeypatch, "GOS102A", capsys)
    assert "FILTERS: none to add" in out
    assert "territory and time only" in out
    assert "select={" not in out


def test_time_and_unit_are_not_offered_as_filters(monkeypatch, capsys):
    """level= covers territory, and nobody filters the unit of measure."""
    out = _how(monkeypatch, "POP107D", capsys)
    assert "'Ani'" not in out
    assert "UM: Numar persoane, flat" not in out
    assert "Localitati, flat" not in out


# ------------------------------------------------------- the typical call

def test_the_typical_call_combines_the_finest_level_and_the_groups(monkeypatch,
                                                                    capsys):
    out = _how(monkeypatch, "POP107D", capsys)

    assert "A TYPICAL CALL for this indicator:" in out
    assert ("m.download(level='localitate', "
            f"select={{{VARSTA!r}: 'groups'}}, folder='data/pop107d')") in out
    assert f"19 of the 104 options of {VARSTA}" in out


def test_the_typical_call_uses_get_when_it_fits(monkeypatch, capsys):
    """FOM104F is two requests, so the example is a get(), not a download()."""
    out = _how(monkeypatch, "FOM104F", capsys)
    example = out[out.index("A TYPICAL CALL"):]
    assert "m.get(level='judet')" in example
    assert "m.download(" not in example
    assert "2 requests" in example


def test_the_typical_call_is_planned_not_guessed(monkeypatch, capsys):
    """Its request count is that exact call's, filter included.

    POP107D is 380 requests whole and 87 with the age groups: the filter is
    what makes it reasonable, and saying 380 next to a call that costs 87 would
    make the whole manual untrustworthy.
    """
    out = _how(monkeypatch, "POP107D", capsys)
    _api(monkeypatch)
    m = t.matrix("POP107D")

    filtered = m._requests_for(["localitate"], {VARSTA: "groups"})
    assert filtered == 87
    assert m._requests_for(m._wanted_levels("finest", None, m.fetch_plan())) \
        == 380
    assert f"{filtered} requests: 19 of the 104" in out


def test_the_typical_call_on_an_indicator_with_no_filter(monkeypatch, capsys):
    out = _how(monkeypatch, "GOS102A", capsys)
    example = out[out.index("A TYPICAL CALL"):]
    assert "m.get(level='localitate')" in example
    assert "nothing filtered out" in example
    assert "select=" not in example


# ------------------------------------------------------- nothing hardcoded

def test_the_manual_reads_the_matrix_it_is_given(monkeypatch, capsys):
    """Same code, edited fixture, different manual. Nothing is per indicator."""
    edited = dict(META["POP107D"])
    edited["dimensionsMap"] = [
        # the age dimension cut down to Total plus two groups plus two ages
        dict(META["POP107D"]["dimensionsMap"][0],
             options=[o for o in META["POP107D"]["dimensionsMap"][0]["options"]
                      if o["label"].strip() in ("Total", "0- 4 ani", "0 ani",
                                                "1 ani", "5- 9 ani")]),
    ] + META["POP107D"]["dimensionsMap"][1:]

    out = _how(monkeypatch, "POP107D", capsys, {"POP107D": edited})
    assert f"{VARSTA}, hierarchical, 5 options" in out
    assert "3 options" in out          # Total plus the two groups
    assert "2 options" in out          # the two single ages
    assert "104" not in out


# ------------------------------------------------------------- regression

def test_the_rest_of_how_is_still_there(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys)
    assert "How to download POP107D:" in out
    assert "m = t.matrix('POP107D')" in out
    assert "THIS ONE IS LARGE: 380 requests" in out
    assert "m.get(raw=True)" in out
    assert "strategy: by_county, 380 requests" in out
    assert "county and locality are separate dimensions here" in out


def test_how_still_runs_on_every_family(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    for cod in ("FOM104D", "SOM101B", "FOM101A", "FOM104F", "TMP1173"):
        t.matrix(cod).how()
        assert cod in capsys.readouterr().out


def test_units_per_level_matches_where(monkeypatch, capsys):
    """The counting is shared with where(), not written twice."""
    _api(monkeypatch, {"FOM104D": FOM104D_MIC})
    m = t.matrix("FOM104D")
    judete = m.dimensions[0]
    assert manual.dimension_units(judete, m.details) == {
        "national": 1, "judet": 2}
    # and the locality dimension counts localities, without its total
    localitati = m.dimensions[1]
    assert territory.is_locality_dimension(localitati, m.details)
    assert manual.dimension_units(localitati, m.details) == {"localitate": 4}
