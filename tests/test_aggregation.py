"""Offline tests for the aggregation check that closes every download().

The check is what stands between a download of a hundred requests and a file
that looks finished and is not. Here it is exercised on its own, with frames
built by hand, so each failure mode is named rather than hoped for.
"""
import pandas as pd

import pytempo as t
from pytempo import incremental, selection

from .test_guidance import _api
from .test_smoke import FOM104D_MIC, SOM101B

META = {"FOM104D": FOM104D_MIC, "SOM101B": SOM101B}

TERITORIU = "Macroregiuni, regiuni de dezvoltare si judete"


def _frame(judete=("Bihor", "Cluj"), ani=("Anul 2020",)):
    """A frame shaped like SOM101B output: three dimensions plus the value."""
    randuri = [(j, a) for j in judete for a in ani]
    return pd.DataFrame({
        TERITORIU: [r[0] for r in randuri],
        "Ani": [r[1] for r in randuri],
        "UM: Numar persoane": ["Numar persoane"] * len(randuri),
        "Valoare": [float(i) for i in range(len(randuri))],
    })


def _matrix(monkeypatch, cod="SOM101B"):
    _api(monkeypatch, META)
    return t.matrix(cod)


# ------------------------------------------------------- nothing to report

def test_a_clean_join_reports_nothing(monkeypatch):
    m = _matrix(monkeypatch)
    df = _frame()
    assert incremental._verify_aggregation(df, m, planned=2,
                                           slice_rows=[1, 1]) == []


# ------------------------------------------------------------ completeness

def test_missing_slices_mark_the_result_incomplete(monkeypatch):
    m = _matrix(monkeypatch)
    df = _frame()
    lipsa = [{"index": 3, "encQuery": "9", "error": "ServerUnavailable: x"}]
    problems = incremental._verify_aggregation(df, m, planned=3,
                                               slice_rows=[1, 1],
                                               missing=lipsa)
    assert len(problems) == 1
    assert problems[0].startswith("INCOMPLETE")
    assert "2 of 3 slices" in problems[0]
    assert "Requests missing: 3" in problems[0]


def test_an_incomplete_download_says_so_through_the_frame(monkeypatch,
                                                          tmp_path):
    """The verdict travels with the frame, not only through the printout."""
    from pytempo import chunking, client

    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        if len(cereri) == 2:
            raise client.ServerUnavailable("the INS server did not answer")
        return ("Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
                f"J{len(cereri)}, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, "
                f"Numar persoane, {len(cereri)}\n")

    monkeypatch.setattr(client, "post_pivot", fake_post)
    df = t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)

    assert df.attrs["complete"] is False
    assert [w[:10] for w in df.attrs["aggregation_warnings"]] == ["INCOMPLETE"]
    assert df.attrs["missing_requests"][0]["index"] == 2


def test_a_complete_download_says_so_too(monkeypatch, tmp_path):
    from pytempo import chunking, client

    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    numar = [0]

    def fake_post(payload, **kw):
        numar[0] += 1
        return ("Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
                f"J{numar[0]}, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, "
                f"Numar persoane, {numar[0]}\n")

    monkeypatch.setattr(client, "post_pivot", fake_post)
    df = t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)

    assert df.attrs["complete"] is True
    assert df.attrs["aggregation_warnings"] == []


# ------------------------------------------------------ rows and duplicates

def test_rows_lost_on_the_join_are_reported(monkeypatch):
    m = _matrix(monkeypatch)
    df = _frame()                       # 2 rows
    problems = incremental._verify_aggregation(df, m, planned=2,
                                               slice_rows=[2, 3])
    assert len(problems) == 1
    assert problems[0].startswith("ROWS")
    assert "2 rows" in problems[0] and "5" in problems[0]


def test_rows_doubled_on_the_join_are_reported(monkeypatch):
    m = _matrix(monkeypatch)
    df = _frame(judete=("Bihor", "Cluj", "Alba", "Arad"))
    problems = incremental._verify_aggregation(df, m, planned=2,
                                               slice_rows=[1, 1])
    assert problems[0].startswith("ROWS")


def test_duplicate_keys_are_counted(monkeypatch):
    """The same combination of dimensions cannot legitimately occur twice."""
    m = _matrix(monkeypatch)
    df = _frame()
    dublat = pd.concat([df, df], ignore_index=True)
    problems = incremental._verify_aggregation(dublat, m, planned=2,
                                               slice_rows=[2, 2])
    assert len(problems) == 1
    assert problems[0].startswith("DUPLICATES: 2 rows")


def test_a_duplicate_is_a_key_not_a_value(monkeypatch):
    """Two rows with the same value but different keys are not duplicates."""
    m = _matrix(monkeypatch)
    df = _frame(judete=("Bihor", "Cluj"))
    df["Valoare"] = [7.0, 7.0]
    assert incremental._verify_aggregation(df, m, planned=1,
                                           slice_rows=[2]) == []


# ------------------------------------------------------------------ select

def _restricted(monkeypatch, keep):
    _api(monkeypatch, META)
    m = t.matrix("SOM101B")
    return selection.restrict(m, {TERITORIU: keep})


def test_a_select_that_came_back_whole_passes(monkeypatch):
    m = _restricted(monkeypatch, ["Bihor", "Cluj"])
    df = _frame(judete=("Bihor", "Cluj"))
    assert incremental._verify_aggregation(
        df, m, planned=1, slice_rows=[2],
        select={TERITORIU: ["Bihor", "Cluj"]}) == []


def test_a_select_that_did_not_reach_the_query_is_reported(monkeypatch):
    """More distinct values than were selected: the filter never arrived."""
    m = _restricted(monkeypatch, ["Bihor", "Cluj"])
    df = _frame(judete=("Bihor", "Cluj", "TOTAL"))
    problems = incremental._verify_aggregation(
        df, m, planned=1, slice_rows=[3],
        select={TERITORIU: ["Bihor", "Cluj"]})
    assert len(problems) == 1
    assert problems[0].startswith("SELECT")
    assert "3 distinct values, 2 were selected" in problems[0]
    assert "did not reach the query" in problems[0]


def test_a_select_that_cut_too_deep_is_reported(monkeypatch):
    m = _restricted(monkeypatch, ["Bihor", "Cluj"])
    df = _frame(judete=("Bihor",))
    problems = incremental._verify_aggregation(
        df, m, planned=1, slice_rows=[1],
        select={TERITORIU: ["Bihor", "Cluj"]})
    assert len(problems) == 1
    assert problems[0].startswith("SELECT")
    assert "1 distinct values of the 2 selected" in problems[0]
    # sparse data is a legitimate explanation, and it is offered as one
    assert "no data for the rest" in problems[0]


def test_select_is_checked_on_the_dimension_the_key_names(monkeypatch):
    """A substring key resolves the same way it does in select itself."""
    m = _restricted(monkeypatch, ["Bihor", "Cluj"])
    df = _frame(judete=("Bihor", "Cluj"))
    assert incremental._verify_aggregation(
        df, m, planned=1, slice_rows=[2], select={"Macroregiuni": ["x"]}) == []


# ------------------------------------------------------- the streaming path

def test_without_a_frame_the_two_checks_say_they_did_not_run(monkeypatch):
    """return_df=False never assembles the frame, and does not pretend to."""
    m = _matrix(monkeypatch)
    problems = incremental._verify_aggregation(None, m, planned=2,
                                               slice_rows=[3, 4])
    assert len(problems) == 1
    assert problems[0].startswith("not checked")
    assert "return_df=False" in problems[0]


def test_the_streaming_path_still_checks_completeness(monkeypatch):
    m = _matrix(monkeypatch)
    lipsa = [{"index": 1, "encQuery": "9", "error": "x"}]
    problems = incremental._verify_aggregation(None, m, planned=2,
                                               slice_rows=[3], missing=lipsa)
    assert [p[:10] for p in problems] == ["INCOMPLETE", "not checke"]


# ---------------------------------------------------------- what gets printed

def test_the_verdict_is_printed_even_when_quiet(monkeypatch, tmp_path, capsys):
    """progress=False silences progress, never a frame that is wrong."""
    from pytempo import chunking, client

    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    # the same two rows for every request, so the joined frame repeats keys
    monkeypatch.setattr(client, "post_pivot", lambda payload, **kw: (
        "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
        "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, Numar persoane, 31.5\n"))

    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)
    iesire = capsys.readouterr().out
    assert "aggregation check:" in iesire
    assert "DUPLICATES: 2 rows" in iesire


def test_a_clean_run_says_so_when_progress_is_on(monkeypatch, tmp_path,
                                                 capsys):
    from pytempo import chunking, client

    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    numar = [0]

    def fake_post(payload, **kw):
        numar[0] += 1
        return ("Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
                f"J{numar[0]}, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, "
                f"Numar persoane, 1\n")

    monkeypatch.setattr(client, "post_pivot", fake_post)
    t.matrix("FOM104D").download(folder=tmp_path / "d")
    iesire = capsys.readouterr().out
    assert "aggregation check: 3 rows, complete, no duplicates" in iesire
