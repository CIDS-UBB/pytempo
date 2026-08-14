"""Offline tests for select=, which trims a dimension before the query is built.

The fixture is shaped like a real demographic indicator: a big age dimension,
which is exactly the case select exists for, since asking for one age group
used to cost the whole download.
"""
import pytest

import pytempo as t
from pytempo import chunking, selection

from .test_guidance import _api, _post
from .test_smoke import CSV_FOM104D, FOM104D_MIC, _IERARHIC

# Total plus eighteen five year groups, as INS writes them
GRUPE = [{"label": "Total", "nomItemId": 60, "offset": 1, "parentId": None}] + [
    {"label": f"{i * 5}-{i * 5 + 4} ani", "nomItemId": 61 + i, "offset": i + 2,
     "parentId": None}
    for i in range(18)
]

POP999T = {
    "matrixName": "Populatia rezidenta pe grupe de varsta, sexe si judete",
    "definitie": "", "metodologie": "", "observatii": "",
    "ultimaActualizare": "01-06-2026",
    "periodicitati": ["Anuala"], "surseDeDate": [],
    "ancestors": [{"name": "A. STATISTICA SOCIALA", "code": "1"}],
    "details": {"nomJud": 0, "nomLoc": 0, "matTime": 4, "matCaen1": 0,
                "matCaen2": 0, "matSiruta": 0, "matRegJ": 3, "matMaxDim": 5,
                "matUMSpec": 0},
    "dimensionsMap": [
        # the trailing space is real: INS labels carry them
        {"dimCode": 1, "label": "Sexe ", "options": [
            {"label": "Total", "nomItemId": 50, "offset": 1, "parentId": None},
            {"label": "Masculin", "nomItemId": 51, "offset": 2, "parentId": None},
            {"label": "Feminin", "nomItemId": 52, "offset": 3, "parentId": None},
        ]},
        {"dimCode": 2, "label": "Grupe de varsta (ani impliniti)",
         "options": GRUPE},
        {"dimCode": 3, "label": "Macroregiuni, regiuni de dezvoltare si judete",
         "options": _IERARHIC},
        {"dimCode": 4, "label": "Ani", "options": [
            {"label": "Anul 2020", "nomItemId": 20, "offset": 1, "parentId": None},
            {"label": "Anul 2021", "nomItemId": 21, "offset": 2, "parentId": None},
            {"label": "Anul 2022", "nomItemId": 22, "offset": 3, "parentId": None},
        ]},
        {"dimCode": 5, "label": "UM: Numar persoane", "options": [
            {"label": "Numar persoane", "nomItemId": 30, "offset": 1,
             "parentId": None}]},
    ],
}

# five dimensions, so six columns
CSV_POP999T = (
    "Sexe, Grupe de varsta (ani impliniti), "
    "Macroregiuni  regiuni de dezvoltare si judete, Ani, "
    "UM: Numar persoane, Valoare\n"
    "Masculin, 25-29 ani, Cluj, Anul 2020, Numar persoane, 12345\n"
)

META = {"POP999T": POP999T, "FOM104D": FOM104D_MIC}
CSV = {"POP999T": CSV_POP999T, "FOM104D": CSV_FOM104D}

VARSTA = "Grupe de varsta (ani impliniti)"
TERITORIU = "Macroregiuni, regiuni de dezvoltare si judete"


def _setup(monkeypatch):
    """Metadata and pivot both faked. Returns the list of captured payloads."""
    _api(monkeypatch, META)
    return _post(monkeypatch, CSV)


def _blocks(payload) -> list[list[str]]:
    """The encQuery, back into one list of ids per dimension."""
    return [block.split(",") for block in payload["encQuery"].split(":")]


# ------------------------------------------------------- choosing options

def test_select_by_ids_narrows_the_dimension(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={VARSTA: [61, 62]}, progress=False)

    assert len(cereri) == 1
    varsta = _blocks(cereri[0])[1]
    assert varsta == ["61", "62"]
    # every other dimension is untouched
    assert _blocks(cereri[0])[0] == ["50", "51", "52"]


def test_select_by_ids_shrinks_the_cell_count_and_the_plan(monkeypatch):
    """The chunking works on the reduced set, not on the whole indicator."""
    cereri = _setup(monkeypatch)
    monkeypatch.setattr(chunking, "MAX_CELLS", 100)

    # 3 sexes x 19 age groups x 5 territories x 3 years = 855 cells
    t.matrix("POP999T").get(level=None, progress=False)
    assert len(cereri) > 1

    cereri.clear()
    # two age groups bring it to 90, under the threshold: one request
    t.matrix("POP999T").get(level=None, select={VARSTA: [61, 62]},
                            progress=False)
    assert len(cereri) == 1


def test_select_by_labels_resolves_to_the_right_ids(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={VARSTA: ["25-29 ani", "30-34 ani"]},
                            progress=False)
    assert _blocks(cereri[0])[1] == ["66", "67"]


def test_select_by_an_unknown_label_names_it(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select={VARSTA: ["25-29 de ani"]},
                                progress=False)
    assert "25-29 de ani" in str(info.value)
    assert "'25-29 ani'" in str(info.value)      # the suggestion


def test_select_by_an_unknown_id_names_it(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select={VARSTA: [61, 9999]}, progress=False)
    assert "9999" in str(info.value)


def test_select_with_a_predicate_keeps_the_matching_options(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(
        select={"Ani": lambda o: o.label in ("Anul 2021", "Anul 2022")},
        progress=False)
    assert _blocks(cereri[0])[3] == ["21", "22"]


def test_a_predicate_that_keeps_nothing_is_an_error(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select={"Ani": lambda o: False}, progress=False)
    assert "predicate kept none" in str(info.value)


def test_a_single_value_stands_for_a_list_of_one(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={"Sexe": "Masculin"}, progress=False)
    assert _blocks(cereri[0])[0] == ["51"]


def test_the_chosen_options_keep_the_order_ins_gave(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={"Ani": [22, 20]}, progress=False)
    assert _blocks(cereri[0])[3] == ["20", "22"]


# ---------------------------------------------------- naming the dimension

def test_dimension_key_matches_the_label_exactly(monkeypatch):
    cereri = _setup(monkeypatch)
    # 'sexe' finds 'Sexe ', trailing space and capital included
    t.matrix("POP999T").get(select={"sexe": ["Feminin"]}, progress=False)
    assert _blocks(cereri[0])[0] == ["52"]


def test_an_exact_match_beats_a_substring(monkeypatch):
    """'Ani' is also inside 'Grupe de varsta (ani impliniti)'."""
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={"Ani": [20]}, progress=False)
    assert _blocks(cereri[0])[3] == ["20"]
    assert len(_blocks(cereri[0])[1]) == 19      # the age dimension is whole


def test_dimension_key_matches_a_unique_substring(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={"varsta": [61]}, progress=False)
    assert _blocks(cereri[0])[1] == ["61"]


def test_an_ambiguous_substring_lists_the_candidates(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select={"de": [61]}, progress=False)
    message = str(info.value)
    assert "matches 2 dimensions" in message
    assert VARSTA in message and TERITORIU in message


def test_an_unknown_dimension_lists_the_available_ones(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select={"Ocupatie": [1]}, progress=False)
    message = str(info.value)
    assert "Ocupatie" in message
    assert "'Sexe'" in message and "'Ani'" in message


def test_select_must_be_a_dict(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP999T").get(select=[VARSTA], progress=False)
    assert "select is a dict" in str(info.value)


# ------------------------------------------------------------- composition

def test_select_on_two_dimensions_composes(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(
        select={"Sexe": ["Masculin"], VARSTA: [61, 62]}, progress=False)
    blocks = _blocks(cereri[0])
    assert blocks[0] == ["51"]
    assert blocks[1] == ["61", "62"]
    assert blocks[3] == ["20", "21", "22"]       # untouched


def test_select_composes_with_a_level(monkeypatch):
    """select trims the options, level then works on what is left."""
    cereri = _setup(monkeypatch)
    t.matrix("POP999T").get(select={TERITORIU: ["Cluj", "Bihor", "TOTAL"]},
                            level="judet", progress=False)
    assert _blocks(cereri[0])[2] == ["4", "5"]   # TOTAL is not a county


def test_select_leaves_the_matrix_alone(monkeypatch):
    _setup(monkeypatch)
    m = t.matrix("POP999T")
    m.get(select={VARSTA: [61]}, progress=False)
    assert len(m.dimensions[1].options) == 19
    # and a second call with no select still sees everything
    assert len(m._build_selection([])[1]) == 19


def test_without_select_nothing_changes(monkeypatch):
    """Regression: the default download is exactly what it was."""
    cereri = _setup(monkeypatch)
    m = t.matrix("POP999T")
    m.get(level=None, progress=False)
    full = chunking.build_encquery(
        [[o.nom_item_id for o in d.options] for d in m.dimensions])
    assert cereri[0]["encQuery"] == full

    cereri.clear()
    m.get(level=None, select=None, progress=False)
    assert cereri[0]["encQuery"] == full


def test_select_reports_what_it_trimmed(monkeypatch, capsys):
    _setup(monkeypatch)
    t.matrix("POP999T").get(select={VARSTA: [61, 62]})
    iesire = capsys.readouterr().out
    assert "select: Grupe de varsta (ani impliniti) limited to 2 of 19" in iesire


# ------------------------------------------------ alongside the county split

def test_select_elsewhere_still_splits_by_county(monkeypatch):
    """FOM104D reaches localities: the split survives a select on the years."""
    cereri = _setup(monkeypatch)
    monkeypatch.setattr(chunking, "MAX_CELLS", 4)
    t.matrix("FOM104D").get(level="localitate", select={"Ani": ["Anul 2024"]},
                            progress=False)

    # one request per county holding localities, Alba and Arad
    assert len(cereri) == 2
    counties = [_blocks(c)[0] for c in cereri]
    assert counties == [["3064"], ["3065"]]
    # and every one of them carries only the selected year
    assert all(_blocks(c)[2] == ["4266"] for c in cereri)


def test_the_payload_carries_only_the_selected_ids(monkeypatch):
    cereri = _setup(monkeypatch)
    t.matrix("FOM104D").get(level="judet", select={"Ani": ["Anul 2023"]},
                            progress=False)
    assert len(cereri) == 1
    assert _blocks(cereri[0])[2] == ["4247"]
    assert "4266" not in cereri[0]["encQuery"]


# ----------------------------------------------------- the module by itself

def test_restrict_returns_a_copy(monkeypatch):
    _setup(monkeypatch)
    m = t.matrix("POP999T")
    smaller = selection.restrict(m, {VARSTA: [61]})
    assert smaller is not m
    assert len(smaller.dimensions[1].options) == 1
    assert len(m.dimensions[1].options) == 19
    # everything else comes along untouched
    assert smaller.code == m.code and smaller.details == m.details


def test_naming_one_dimension_twice_is_an_error(monkeypatch):
    _setup(monkeypatch)
    m = t.matrix("POP999T")
    with pytest.raises(ValueError) as info:
        selection.restrict(m, {"varsta": [61], VARSTA: [62]})
    assert "twice" in str(info.value)


def test_an_empty_list_is_an_error(monkeypatch):
    _setup(monkeypatch)
    m = t.matrix("POP999T")
    with pytest.raises(ValueError) as info:
        selection.restrict(m, {"Sexe": []})
    assert "the list is empty" in str(info.value)


def test_a_non_text_key_is_an_error(monkeypatch):
    _setup(monkeypatch)
    m = t.matrix("POP999T")
    with pytest.raises(ValueError) as info:
        selection.restrict(m, {1: [61]})
    assert "dimension labels, as text" in str(info.value)
