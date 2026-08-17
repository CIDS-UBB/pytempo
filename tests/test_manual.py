"""Offline tests for how() as the menu of one indicator.

how() knew what to say before it knew how to say it. On TUR101B it printed
'Tipuri de structuri de primire turistica' four times, once per select line,
and said 'groups: 17 options' without a word about what those seventeen are.
Everything correct, nothing easy.

What is tested here is both halves: that every number is read off the fixture
it came from, and that the shape of the page is the friendly one, the call
first, each name in full once and short thereafter, counts with real values
next to them.
"""
import json
from pathlib import Path

import pytempo as t
from pytempo import catalog, client, endpoints, hierarchy, manual, territory

from .test_guidance import _registry
from .test_smoke import FOM104D_MIC

FIXTURES = Path(__file__).parent / "fixtures"
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("POP107D", "FOM104F", "GOS102A",
                                   "TUR101B", "AGR101A")}

TIPURI = "Tipuri de structuri de primire turistica"
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


def _how(monkeypatch, cod, capsys, meta=None, full=False) -> str:
    _api(monkeypatch, meta)
    t.matrix(cod).how(full=full)
    return capsys.readouterr().out


# ------------------------------------------------------------ short names

def test_a_dimension_gets_a_name_you_would_type(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("TUR101B")
    aliases = [manual.alias_for(m, d) for d in manual.filterable(m)]
    assert aliases == ["tipuri", "categorii", "destinatii"]


def test_the_short_name_resolves_to_the_dimension_it_names(monkeypatch):
    """Printed and then typed, it has to land on the same dimension."""
    _api(monkeypatch)
    for cod in ("TUR101B", "POP107D", "FOM104F", "AGR101A"):
        m = t.matrix(cod)
        for dimension in manual.filterable(m):
            key = manual.alias_for(m, dimension)
            assert m._find_dimension(key) is dimension, (cod, key)
            # and select= accepts it, which is the point of showing it
            assert len(m.options(key)) == len(dimension.options)


def test_the_long_name_is_the_fallback(monkeypatch):
    """Two dimensions that share every word keep their full labels."""
    twins = dict(META["TUR101B"])
    twins["dimensionsMap"] = [
        dict(META["TUR101B"]["dimensionsMap"][0], label="Categorii de confort"),
        META["TUR101B"]["dimensionsMap"][1],
    ] + META["TUR101B"]["dimensionsMap"][2:]

    _api(monkeypatch, {"TUR101B": twins})
    m = t.matrix("TUR101B")
    assert manual.alias_for(m, m.dimensions[0]) == "Categorii de confort"


def test_the_long_name_appears_once_not_once_per_line(monkeypatch, capsys):
    """The complaint, in a test: four repetitions of a forty character name."""
    out = _how(monkeypatch, "TUR101B", capsys)
    assert out.count(TIPURI) == 1
    # the filter block names it once and then works in the short name
    filtre = out[out.index("FILTERS"):]
    assert filtre.count(TIPURI) == 1
    assert filtre.count("tipuri") >= 2


# --------------------------------------------------------- the call first

def test_the_call_comes_first_and_says_why(monkeypatch, capsys):
    out = _how(monkeypatch, "TUR101B", capsys)

    assert out.index("THE CALL") < out.index("FILTERS")
    assert ("m.get(select={'tipuri': 'groups', 'categorii': 'total', "
            "'destinatii': 'total'})") in out
    assert "1 request" in out
    # the reason, in words, not as a shrug
    # the reason is wrapped for reading, so it is read back unwrapped
    prose = " ".join(out.split())
    assert "Why this shape:" in prose
    assert "'groups' on tipuri keeps the 17 aggregates" in prose
    assert "'total' on categorii and destinatii" in prose
    assert "multiplies the rows without adding an answer" in prose


def test_the_call_varies_one_dimension_and_pins_the_rest(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("TUR101B")
    select, reasons = manual.recommended(m, None)

    assert select == {"tipuri": "groups", "categorii": "total",
                      "destinatii": "total"}
    assert len(reasons) == 2
    # and it is a call that runs: the words resolve, the plan is one request
    assert m._requests_for([], select) == 1


def test_a_dimension_with_no_total_is_left_alone(monkeypatch):
    """Pinning it to a total it does not have would be an error, not advice."""
    fara_total = dict(META["TUR101B"])
    confort = dict(META["TUR101B"]["dimensionsMap"][1])
    confort["options"] = [o for o in confort["options"]
                          if o["label"].strip() != "Total"]
    fara_total["dimensionsMap"] = [META["TUR101B"]["dimensionsMap"][0],
                                   confort] + \
        META["TUR101B"]["dimensionsMap"][2:]

    _api(monkeypatch, {"TUR101B": fara_total})
    m = t.matrix("TUR101B")
    select, _ = manual.recommended(m, None)
    assert "categorii" not in select
    assert select["tipuri"] == "groups"


def test_the_call_on_a_large_one_shows_what_the_filter_buys(monkeypatch,
                                                             capsys):
    """380 requests whole, 42 filtered: the two numbers are the lesson."""
    out = _how(monkeypatch, "POP107D", capsys)

    assert ("m.get(level='localitate', select={'varste': 'groups', "
            "'sexe': 'total'})") in out
    assert "42 requests, not the 380 the whole indicator costs" in out
    assert "that is what the filter buys" in out


def test_the_call_is_just_a_level_when_there_is_nothing_to_filter(monkeypatch,
                                                                   capsys):
    """GOS102A is territory and time, so the call is the finest level alone."""
    out = _how(monkeypatch, "GOS102A", capsys)
    example = out[out.index("THE CALL"):out.index("TERRITORIAL")]
    assert "m.get(level='localitate')" in example
    assert "42 requests" in example


# ----------------------------------------------------------------- levels

def test_the_levels_are_listed_with_their_real_sizes(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys)
    _api(monkeypatch)
    counts = manual.units_per_level(t.matrix("POP107D"))
    assert counts == {"national": 1, "judet": 42, "localitate": 3181}

    assert "TERRITORIAL LEVEL, pick one:" in out
    assert "national          1 unit" in out
    assert "judet           42 units" in out
    assert "localitate    3181 units" in out
    assert "m.get(level=None)" in out


def test_each_level_says_what_it_costs(monkeypatch, capsys):
    """Which level is one request and which is hundreds."""
    out = _how(monkeypatch, "POP107D", capsys)
    _api(monkeypatch)
    m = t.matrix("POP107D")

    assert m._requests_for(["judet"]) == 5
    assert m._requests_for(["localitate"]) == 379
    assert "5 requests   m.get(level='judet')" in out
    assert ("379 requests   m.download(level='localitate', "
            "folder='data/pop107d')") in out
    assert "default, the finest" in out


def test_no_level_table_when_there_is_no_usable_level(monkeypatch, capsys):
    out = _how(monkeypatch, "TUR101B", capsys)
    assert "TERRITORIAL LEVEL, pick one" not in out
    assert "NO TERRITORIAL LEVEL: this indicator is not territorial" in out
    assert "m.get(level=" not in out


# ---------------------------------------------------------------- filters

def test_a_hierarchical_dimension_shows_its_keywords_with_values(monkeypatch,
                                                                  capsys):
    """A count is not an answer: 17 what?"""
    out = _how(monkeypatch, "TUR101B", capsys)
    _api(monkeypatch)
    tipuri = t.matrix("TUR101B")._find_dimension("tipuri")

    assert len(hierarchy.pick(tipuri, "groups")) == 17
    assert len(hierarchy.pick(tipuri, "leaves")) == 2

    assert "tipuri      Tipuri de structuri de primire turistica" in out
    assert "19 options on 2 levels" in out
    assert "'groups'   17: Total, Hoteluri, Hoteluri pentru tineret, ..." in out
    assert "'leaves'    2: Pensiuni turistice, Pensiuni agroturistice" in out
    assert "'total'     1: Total" in out


def test_a_small_flat_dimension_shows_its_values_and_a_list(monkeypatch,
                                                             capsys):
    out = _how(monkeypatch, "TUR101B", capsys)
    assert "categorii   Categorii de confort" in out
    assert "19 options, one level" in out
    assert "values: Total, 5 stele, 4 stele, ..." in out
    # the example picks a real value, and not the total, which filters nothing
    assert "a few:  select={'categorii': ['5 stele']}" in out
    assert "or one: select={'categorii': 'total'}" in out


def test_a_long_value_is_cut_at_a_word(monkeypatch, capsys):
    """'Statiuni din zona litorala, e...' reads like a bug."""
    out = _how(monkeypatch, "TUR101B", capsys)
    assert "Statiuni din zona litorala..." in out
    assert "litorala, e..." not in out


def test_a_large_flat_dimension_sends_you_to_options(monkeypatch, capsys):
    """FOM104F's CAEN has 68 options and no levels: listing them helps nobody."""
    out = _how(monkeypatch, "FOM104F", capsys)
    assert "68 options, one level" in out
    assert "too many to list here, see m.options('caen')" in out
    assert out.count(CAEN) == 1


def test_an_indicator_with_nothing_to_filter_says_so(monkeypatch, capsys):
    out = _how(monkeypatch, "GOS102A", capsys)
    assert "FILTERS: none to add" in out
    assert "territory and time only" in out
    assert "select={" not in out


def test_time_and_unit_are_not_offered_as_filters(monkeypatch, capsys):
    """level= covers territory, and nobody filters the unit of measure."""
    out = _how(monkeypatch, "POP107D", capsys)
    assert "Ani" not in out.split("FILTERS")[1]
    assert "UM: Numar persoane" not in out
    assert "Localitati" not in out.split("FILTERS")[1]


# ------------------------------------------------------- short versus full

def test_the_short_form_leaves_the_mechanics_out(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys)
    assert "strategy:" not in out
    assert "m.how(full=True)" in out


def test_the_full_form_adds_them_back(monkeypatch, capsys):
    out = _how(monkeypatch, "POP107D", capsys, full=True)
    assert "strategy: by_county, 380 requests for that default call" in out
    assert "m = t.matrix('POP107D')" in out
    assert "df = m.get()" in out
    # and it does not offer itself again
    assert "m.how(full=True)" not in out


def test_the_two_dimension_note_is_detail_not_headline(monkeypatch, capsys):
    scurt = _how(monkeypatch, "POP107D", capsys)
    lung = _how(monkeypatch, "POP107D", capsys, full=True)
    assert "county and locality are separate dimensions" not in scurt
    assert "county and locality are separate dimensions" in lung


# ------------------------------------------------------- nothing hardcoded

def test_the_manual_reads_the_matrix_it_is_given(monkeypatch, capsys):
    """Same code, edited fixture, different manual."""
    edited = dict(META["POP107D"])
    edited["dimensionsMap"] = [
        dict(META["POP107D"]["dimensionsMap"][0],
             options=[o for o in META["POP107D"]["dimensionsMap"][0]["options"]
                      if o["label"].strip() in ("Total", "0- 4 ani", "0 ani",
                                                "1 ani", "5- 9 ani")]),
    ] + META["POP107D"]["dimensionsMap"][1:]

    out = _how(monkeypatch, "POP107D", capsys, {"POP107D": edited})
    assert "104 options" not in out
    assert "5 options on 3 levels" in out
    assert "'groups'    3: Total, 0- 4 ani, 5- 9 ani" in out
    assert "'leaves'    2: 0 ani, 1 ani" in out


def test_how_still_runs_on_every_family(monkeypatch, tmp_path, capsys):
    _registry(monkeypatch, tmp_path)
    for cod in ("FOM104D", "SOM101B", "FOM101A", "FOM104F", "TMP1173"):
        for full in (False, True):
            t.matrix(cod).how(full=full)
            assert cod in capsys.readouterr().out


def test_units_per_level_matches_where(monkeypatch, capsys):
    """The counting is shared with where(), not written twice."""
    _api(monkeypatch, {"FOM104D": FOM104D_MIC})
    m = t.matrix("FOM104D")
    assert manual.dimension_units(m.dimensions[0], m.details) == {
        "national": 1, "judet": 2}
    localitati = m.dimensions[1]
    assert territory.is_locality_dimension(localitati, m.details)
    assert manual.dimension_units(localitati, m.details) == {"localitate": 4}
