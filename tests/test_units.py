"""Offline tests that pin what the unit of measure role decides. No network.

tests/fixtures/units_before_role_fix.json was generated before the um role
learned to recognize dimensions named 'Unitati de masura', on real metadata:

    FOM121A, FOM118G   'Unitati de masura', two options, then role alt
    LOC108B            'UM: Numar, mp suprafata utila', two options, role um
    SCL101B, TUR101B   a single 'UM: ...' option, role um

For each: the roles, the text of how() and how(full=True), and on a frame built
from the real option labels, what wide() indexes on and what spot_check()
pins. Any change to these is a change the role made, and has to be explained.

One change is deliberate, and it is in the file: with the role fixed, how() on
FOM121A and FOM118G no longer lists 'Unitati de masura' among the filters, the
way it already left out 'UM: ...' on LOC108B. Those two entries were
regenerated after the fix; the rest are as they were before it. Nothing else
moved: not the roles of the 'UM:' dimensions, not wide() or spot_check() here,
and not the call how() puts first.

A second one followed: a unit with more than one option is a selector of
measures, and how() lists it again among the filters, marked as such. FOM121A,
FOM118G and LOC108B were regenerated for that, a block added and nothing else;
SCL101B and TUR101B, with a single unit, are unchanged.
"""
import json
from pathlib import Path

import pytest

import pytempo as t
from pytempo import catalog, client, endpoints, parse, schema, territory

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "units_before_role_fix.json").read_text(
    encoding="utf-8"))
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in GOLDEN}


def _api(monkeypatch):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in META])

    def fake_get_json(url, **kw):
        for cod, date in META.items():
            if url == endpoints.matrix(cod):
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


def _accessor(m):
    frame = schema._sample_frame(m)
    frame[parse.CONFIDENTIAL_COLUMN] = False
    return parse.standardize(frame, m).tempo


@pytest.mark.parametrize("cod", sorted(GOLDEN))
def test_how_is_what_it_was(monkeypatch, capsys, cod):
    _api(monkeypatch)
    m = t.matrix(cod)
    m.how()
    assert capsys.readouterr().out == GOLDEN[cod]["how"]
    m.how(full=True)
    assert capsys.readouterr().out == GOLDEN[cod]["how_full"]


@pytest.mark.parametrize("cod", sorted(GOLDEN))
def test_wide_and_spot_check_columns_are_what_they_were(monkeypatch, cod):
    _api(monkeypatch)
    acc = _accessor(t.matrix(cod))
    unit = acc._unit_base()
    assert acc._index_columns() == GOLDEN[cod]["wide_index"]
    assert (acc._inner_columns(unit) if unit else None) \
        == GOLDEN[cod]["spot_inner"]


# --------------------------------------------- which label is a unit dimension

@pytest.mark.parametrize("label", [
    "UM: Numar persoane", "um: lei", "UM:Numar",
    "Unitati de masura", "  Unitati  de   masura ", "Unități de măsură",
    "Unitati de masura specifice",
    "Unitati de masura (numar,persoane,mii lei, lei RON (incepand cu 2005)",
])
def test_unit_labels_are_recognized(label):
    assert territory.is_unit_label(label)


@pytest.mark.parametrize("label", [
    "Unitati, capacitate, cheltuieli de functionare",
    "Unitati de asistenta speciala pentru minori cu deficiente",
    "Masura in care fac fata cheltuielilor curente",
    "Categorii de unitati administrative", "Sexe", "", None,
])
def test_near_misses_are_not_units(label):
    assert not territory.is_unit_label(label)


def test_unitati_de_masura_now_has_the_um_role(monkeypatch):
    _api(monkeypatch)
    for cod in ("FOM121A", "FOM118G"):
        unit = t.matrix(cod).dimensions[-1]
        assert unit.label.strip() == "Unitati de masura"
        assert unit.role == "um"
    # and the 'UM:' ones are what they were
    for cod in ("LOC108B", "SCL101B", "TUR101B"):
        assert t.matrix(cod).dimensions[-1].role == "um"


def test_unit_text_names_the_units_not_the_dimension(monkeypatch):
    _api(monkeypatch)
    fom121a = t.matrix("FOM121A").dimensions[-1]
    loc108b = t.matrix("LOC108B").dimensions[-1]
    assert territory.unit_text(fom121a) == "Numar persoane, Lei"
    assert territory.unit_text(loc108b) == "Numar, mp suprafata utila"


def test_what_and_the_ddl_comment_say_the_units(monkeypatch, capsys):
    _api(monkeypatch)
    m = t.matrix("FOM121A")
    m.what()
    assert "unit        : Numar persoane, Lei" in capsys.readouterr().out
    assert "'Measured in Numar persoane, Lei'" in m.schema()


def test_a_constant_unitati_de_masura_leaves_the_wide_index(monkeypatch):
    """One option means no choice: like a constant 'UM: ...', it would only
    pad the index of wide(), so it is left out."""
    _api(monkeypatch)
    m = t.matrix("FOM121A")
    frame = schema._sample_frame(m)
    frame["Unitati de masura"] = "Lei"
    frame[parse.CONFIDENTIAL_COLUMN] = False
    acc = parse.standardize(frame, m).tempo
    assert "Unitati de masura" not in acc._index_columns()


# ------------------------------------ the unit that selects among measures

def test_a_measure_selector_is_listed_and_named_as_one(monkeypatch, capsys):
    _api(monkeypatch)
    for cod, key in (("FOM121A", "unitati"), ("LOC108B", "numar")):
        t.matrix(cod).how()
        out = capsys.readouterr().out
        filters = out.split("FILTERS")[1]
        assert f"    {key}" in filters
        assert "a selector of measures, not a fixed unit" in filters
        assert "not comparable" in filters


def test_a_unit_with_one_option_stays_out_of_the_filters(monkeypatch, capsys):
    _api(monkeypatch)
    for cod in ("SCL101B", "TUR101B"):
        t.matrix(cod).how()
        out = capsys.readouterr().out
        assert "selector of measures" not in out
        assert "UM:" not in out.split("FILTERS")[1]


def test_the_selector_stays_out_of_the_suggested_call(monkeypatch, capsys):
    """FOM121A's units go with its first dimension, counts with 'Numar
    persoane', wages with 'Lei': pinning one would drop half of it."""
    _api(monkeypatch)
    t.matrix("FOM121A").how()
    call = capsys.readouterr().out.split("THE CALL")[1].splitlines()[1]
    assert "unitati" not in call


def test_is_measure_selector(monkeypatch):
    from pytempo import manual
    _api(monkeypatch)
    assert manual.is_measure_selector(t.matrix("FOM121A").dimensions[-1])
    assert manual.is_measure_selector(t.matrix("LOC108B").dimensions[-1])
    assert not manual.is_measure_selector(t.matrix("SCL101B").dimensions[-1])
    assert not manual.is_measure_selector(t.matrix("FOM121A").dimensions[0])
