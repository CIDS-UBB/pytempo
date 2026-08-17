"""Offline tests for selecting a kind of option rather than a list of them.

The need is ordinary: the 19 age groups of POP107D and not the 85 single ages.
Writing it by hand meant a loop over the labels, keeping the ones with a hyphen
or the one that says Total, which is a guess about how INS writes names and
breaks on the next dimension.

The fixtures are real metadata. POP107D has the age hierarchy, three levels
deep; AGR101A has land use, two levels, with an aggregate that holds nothing
under it; SCL101B has eighteen levels of education with no hierarchy at all.
Between them they cover what the keywords have to get right.
"""
import json
from pathlib import Path

import pytest

import pytempo as t
from pytempo import catalog, client, endpoints, hierarchy, selection

FIXTURES = Path(__file__).parent / "fixtures"
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("POP107D", "AGR101A", "SCL101B")}

VARSTA = "Varste si grupe de varsta"
FOLOSINTA = "Modul de folosinta a fondului funciar"

CSV_POP107D = (
    "Varste si grupe de varsta, Sexe, Judete, Localitati, Ani, "
    "UM: Numar persoane, Valoare\n"
    "Total, Total, Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, "
    "Numar persoane, 100.0\n"
)


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


def _dim(monkeypatch, cod, label):
    _api(monkeypatch)
    return t.matrix(cod)._find_dimension(label)


# ------------------------------------------------- what the fixture holds

def test_the_age_dimension_has_no_parent_ids(monkeypatch):
    """The foundation, checked rather than assumed.

    parentId is null on this dimension, and on every dimension measured except
    the localities, so the hierarchy cannot come from there. The indentation
    is what INS actually carries, and it is what the fallback reads.
    """
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    assert len(varste.options) == 104
    assert all(o.parent_id is None for o in varste.options)
    assert hierarchy._from_parent_ids(varste) is None

    # three levels, three leading space widths, three spaces per level
    widths = sorted({len(o.label) - len(o.label.lstrip())
                     for o in varste.options})
    assert widths == [0, 3, 6]
    assert hierarchy.is_hierarchical(varste) is True


def test_the_depths_read_off_the_fixture(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    levels = hierarchy.depths(varste)
    by_label = {o.label.strip(): levels[o.nom_item_id] for o in varste.options}

    assert by_label["Total"] == 0
    assert by_label["0- 4 ani"] == 1
    assert by_label["85 ani si peste"] == 1
    assert by_label["0 ani"] == 2
    assert by_label["84 ani"] == 2


# ------------------------------------------------------- the three kinds

def test_groups_on_the_age_dimension_gives_exactly_nineteen(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    groups = hierarchy.pick(varste, "groups")

    assert len(groups) == 19
    labels = [o.label.strip() for o in groups]
    assert labels[0] == "Total"
    assert labels[1] == "0- 4 ani"
    assert labels[-1] == "85 ani si peste"
    # not one single age among them
    assert not any(label.endswith(" ani") and "-" not in label
                   and label != "85 ani si peste" for label in labels[1:])


def test_leaves_on_the_age_dimension_gives_the_eighty_five(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    leaves = hierarchy.pick(varste, "leaves")

    assert len(leaves) == 85
    assert [o.label.strip() for o in leaves][:3] == ["0 ani", "1 ani", "2 ani"]
    assert [o.label.strip() for o in leaves][-1] == "84 ani"
    # groups and leaves partition the dimension, nothing lost, nothing shared
    groups = hierarchy.pick(varste, "groups")
    assert len(groups) + len(leaves) == len(varste.options) == 104
    assert not ({o.nom_item_id for o in groups}
                & {o.nom_item_id for o in leaves})


def test_total_gives_the_total_alone(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    total = hierarchy.pick(varste, "total")
    assert [o.label.strip() for o in total] == ["Total"]


def test_parents_is_the_same_word_as_groups(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    assert hierarchy.pick(varste, "parents") == hierarchy.pick(varste, "groups")


def test_the_kind_is_read_whatever_the_case(monkeypatch):
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    assert len(hierarchy.pick(varste, "GROUPS")) == 19
    assert len(hierarchy.pick(varste, " Leaves ")) == 85


# ----------------------------------------- the same words, another shape

def test_groups_on_land_use_is_the_aggregate_level(monkeypatch):
    """AGR101A proves the words are not about ages.

    Two levels, and 'Alte suprafete' sits at the aggregate level with nothing
    under it. It is a group all the same: leaving it out would give a set of
    groups that does not add up to the total.
    """
    folosinta = _dim(monkeypatch, "AGR101A", FOLOSINTA)
    assert len(folosinta.options) == 14

    groups = [o.label.strip() for o in hierarchy.pick(folosinta, "groups")]
    assert groups == ["Total", "Agricola", "Terenuri neagricole total",
                      "Alte suprafete"]

    leaves = [o.label.strip() for o in hierarchy.pick(folosinta, "leaves")]
    assert len(leaves) == 10
    assert leaves[0] == "Arabila"
    assert "Agricola" not in leaves


def test_an_aggregate_with_nothing_under_it_is_still_a_group(monkeypatch):
    """The case that rules out counting children instead of reading levels."""
    varste = _dim(monkeypatch, "POP107D", VARSTA)
    groups = [o.label.strip() for o in hierarchy.pick(varste, "groups")]
    # INS does not list ages past 85 one by one, so this group holds nothing
    assert "85 ani si peste" in groups
    assert "85 ani si peste" not in [o.label.strip()
                                     for o in hierarchy.pick(varste, "leaves")]


def test_a_hierarchy_from_parent_ids_when_there_is_one(monkeypatch):
    """parentId is read first, where it exists and stays inside the dimension."""
    from .test_smoke import SOM101B

    _api(monkeypatch, {"SOM101B": SOM101B})
    teritoriu = t.matrix("SOM101B")._find_dimension("teritoriu")
    assert any(o.parent_id is not None for o in teritoriu.options)

    groups = [o.label.strip() for o in hierarchy.pick(teritoriu, "groups")]
    leaves = [o.label.strip() for o in hierarchy.pick(teritoriu, "leaves")]
    assert groups == ["TOTAL", "MACROREGIUNEA UNU", "Regiunea NORD-VEST"]
    assert leaves == ["Bihor", "Cluj"]


# ------------------------------------------------------- flat dimensions

def test_groups_on_a_flat_dimension_says_so(monkeypatch):
    niveluri = _dim(monkeypatch, "SCL101B", "Niveluri de educatie")
    with pytest.raises(ValueError) as info:
        hierarchy.pick(niveluri, "groups")

    message = str(info.value)
    assert "not hierarchical" in message
    assert "18 options are all at the same level" in message
    # and what to do instead
    assert "Name the options you want" in message
    assert "m.options('Niveluri de educatie')" in message


def test_leaves_on_a_flat_dimension_says_so(monkeypatch):
    ani = _dim(monkeypatch, "POP107D", "Ani")
    with pytest.raises(ValueError) as info:
        hierarchy.pick(ani, "leaves")
    assert "not hierarchical" in str(info.value)


def test_total_on_a_dimension_that_has_none(monkeypatch):
    ani = _dim(monkeypatch, "POP107D", "Ani")
    with pytest.raises(ValueError) as info:
        hierarchy.pick(ani, "total")
    assert "no total option" in str(info.value)


def test_localities_are_flat_within_themselves(monkeypatch):
    """Their parentId points at the county, which is another dimension."""
    localitati = _dim(monkeypatch, "POP107D", "Localitati")
    assert all(o.parent_id is not None for o in localitati.options)
    assert hierarchy._from_parent_ids(localitati) is None
    assert hierarchy.is_hierarchical(localitati) is False


# ------------------------------------------------------------- through select

def test_select_groups_narrows_the_query(monkeypatch):
    _api(monkeypatch)
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return CSV_POP107D

    monkeypatch.setattr(client, "post_pivot", fake_post)
    t.matrix("POP107D").get(level="judet", select={"varsta": "groups"},
                            progress=False)

    varste = [int(c) for c in cereri[0]["encQuery"].split(":")[0].split(",")]
    assert len(varste) == 19
    m = t.matrix("POP107D")
    expected = [o.nom_item_id
                for o in hierarchy.pick(m._find_dimension(VARSTA), "groups")]
    assert varste == expected


def test_select_leaves_and_total_through_the_same_door(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")
    varste = m._find_dimension(VARSTA)

    assert len(selection.choose_options(varste, "leaves")) == 85
    assert len(selection.choose_options(varste, "total")) == 1
    smaller = selection.restrict(m, {"varsta": "groups"})
    assert len(smaller.dimensions[0].options) == 19
    # the matrix itself is untouched, as with any other select
    assert len(m.dimensions[0].options) == 104


def test_select_reports_the_keyword_like_any_other_trim(monkeypatch, capsys):
    _api(monkeypatch)
    monkeypatch.setattr(client, "post_pivot", lambda p, **kw: CSV_POP107D)
    t.matrix("POP107D").get(level="judet", select={"varsta": "groups"})
    assert "select: Varste si grupe de varsta limited to 19 of 104" in \
        capsys.readouterr().out


def test_a_keyword_on_a_flat_dimension_names_the_dimension(monkeypatch):
    _api(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("SCL101B").get(select={"Niveluri": "groups"}, progress=False)
    assert "not hierarchical" in str(info.value)
    assert "Niveluri de educatie" in str(info.value)


# --------------------------------------------------------- seeing it first

def test_options_kind_lists_what_select_would_keep(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")

    groups = m.options("varsta", kind="groups")
    assert len(groups) == 19
    assert [g.strip() for g in groups][:2] == ["Total", "0- 4 ani"]
    assert len(m.options("varsta", kind="leaves")) == 85
    assert len(m.options("varsta", kind="total")) == 1

    # what you see is what a select would download
    chosen = selection.restrict(m, {"varsta": "groups"})
    assert list(groups) == [o.label for o in chosen.dimensions[0].options]


def test_options_without_kind_is_unchanged(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")
    assert len(m.options("varsta")) == 104
    assert len(m.options("varsta", limit=3)) == 3
    assert len(m.options("varsta", kind="groups", limit=5)) == 5


def test_options_kind_on_a_flat_dimension(monkeypatch):
    _api(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("SCL101B").options("Niveluri", kind="groups")
    assert "not hierarchical" in str(info.value)


def test_an_unknown_kind_lists_the_ones_that_exist(monkeypatch):
    _api(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP107D").options("varsta", kind="aggregates")
    assert "unknown selection kind 'aggregates'" in str(info.value)
    assert "groups, parents, leaves, total" in str(info.value)


# ------------------------------------------------------------- regression

def test_select_by_list_and_predicate_is_untouched(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")
    varste = m._find_dimension(VARSTA)

    by_label = selection.choose_options(varste, ["Total", "0- 4 ani"])
    assert [o.label.strip() for o in by_label] == ["Total", "0- 4 ani"]

    ids = [o.nom_item_id for o in varste.options[:3]]
    assert len(selection.choose_options(varste, ids)) == 3

    predicate = selection.choose_options(varste, lambda o: "85" in o.label)
    assert [o.label.strip() for o in predicate] == ["85 ani si peste"]


def test_a_list_holding_the_word_total_is_still_labels(monkeypatch):
    """Keywords are whole values, never elements of a list."""
    _api(monkeypatch)
    varste = t.matrix("POP107D")._find_dimension(VARSTA)
    kept = selection.choose_options(varste, ["Total", "5- 9 ani"])
    assert [o.label.strip() for o in kept] == ["Total", "5- 9 ani"]


def test_the_word_total_as_a_single_value_still_finds_the_total(monkeypatch):
    """It was a label before and a keyword now, and it means the same option."""
    _api(monkeypatch)
    varste = t.matrix("POP107D")._find_dimension(VARSTA)
    assert [o.label.strip()
            for o in selection.choose_options(varste, "Total")] == ["Total"]


def test_a_plain_label_that_is_not_a_keyword_is_still_a_label(monkeypatch):
    _api(monkeypatch)
    varste = t.matrix("POP107D")._find_dimension(VARSTA)
    kept = selection.choose_options(varste, "25-29 ani")
    assert [o.label.strip() for o in kept] == ["25-29 ani"]
