"""Offline tests for download(), the incremental path with a checkpoint.

Same shape as the rest: fixtures plus a mock on client.post_pivot, no network.
The small FOM104D fixture with a low MAX_CELLS gives a plan of three requests,
which is enough to see slices appear on disk, be skipped on resume, and fail
one at a time without taking the others down.
"""
import pandas as pd
import pytest
import requests

import pytempo as t
from pytempo import chunking, client, incremental

from .test_guidance import _api, _post
from .test_smoke import CSV_FOM104D, CSV_SOM101B, FOM104D_MIC, SOM101B

META = {"FOM104D": FOM104D_MIC, "SOM101B": SOM101B}
CSV = {"FOM104D": CSV_FOM104D, "SOM101B": CSV_SOM101B}


def _setup(monkeypatch, chunked=True):
    """Metadata and pivot faked. Returns the list of captured payloads."""
    _api(monkeypatch, META)
    if chunked:
        monkeypatch.setattr(chunking, "MAX_CELLS", 10)   # 3 requests on FOM104D
    return _post(monkeypatch, CSV)


def _slices(folder):
    return sorted(p.name for p in folder.iterdir() if p.name.startswith("_chunk_"))


# --------------------------------------------------------- the happy path

def test_download_matches_get(monkeypatch, tmp_path):
    """The whole point: through disk or through memory, the same frame."""
    _setup(monkeypatch)
    prin_memorie = t.matrix("FOM104D").get(progress=False)

    _setup(monkeypatch)
    prin_disc = t.matrix("FOM104D").download(folder=tmp_path / "d",
                                             progress=False)
    pd.testing.assert_frame_equal(prin_disc, prin_memorie)


def test_download_sends_the_same_requests_as_get(monkeypatch, tmp_path):
    cereri_get = _setup(monkeypatch)
    t.matrix("FOM104D").get(progress=False)
    prin_get = [c["encQuery"] for c in cereri_get]

    cereri_download = _setup(monkeypatch)
    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)
    assert [c["encQuery"] for c in cereri_download] == prin_get


def test_download_writes_a_slice_per_request(monkeypatch, tmp_path):
    """The slices exist while the download runs, and go once it is done."""
    folder = tmp_path / "d"
    vazute = []

    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    def fake_post(payload, **kw):
        # count what is on disk at the moment each request goes out: the
        # checkpoint has to be written as answers arrive, not at the end
        vazute.append(len(_slices(folder)) if folder.exists() else 0)
        return CSV_FOM104D

    monkeypatch.setattr(client, "post_pivot", fake_post)
    t.matrix("FOM104D").download(folder=folder, progress=False)

    assert vazute == [0, 1, 2]              # one more slice before each request
    assert _slices(folder) == []            # cleaned up after consolidation
    assert (folder / "FOM104D.csv").exists()


def test_the_final_csv_uses_the_project_conventions(monkeypatch, tmp_path):
    _setup(monkeypatch)
    df = t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)

    cale = tmp_path / "d" / "FOM104D.csv"
    brut = cale.read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")             # utf-8-sig
    assert b"sep=" not in brut[:20]                     # no separator line
    inapoi = pd.read_csv(cale, sep=";", encoding="utf-8-sig")
    assert len(inapoi) == len(df)
    assert list(inapoi.columns) == list(df.columns)


def test_out_names_the_csv(monkeypatch, tmp_path):
    _setup(monkeypatch)
    tinta = tmp_path / "undeva" / "salariati.csv"
    t.matrix("FOM104D").download(folder=tmp_path / "d", out=tinta,
                                 progress=False)
    assert tinta.exists()
    assert not (tmp_path / "d" / "FOM104D.csv").exists()


def test_return_df_false_gives_the_path_not_the_frame(monkeypatch, tmp_path):
    _setup(monkeypatch)
    prin_memorie = t.matrix("FOM104D").get(progress=False)

    _setup(monkeypatch)
    cale = t.matrix("FOM104D").download(folder=tmp_path / "d", return_df=False,
                                        progress=False)
    assert cale == tmp_path / "d" / "FOM104D.csv"
    streamed = pd.read_csv(cale, sep=";", encoding="utf-8-sig")
    # written slice by slice, so only the values are compared, not the dtypes
    assert list(streamed.columns) == list(prin_memorie.columns)
    assert len(streamed) == len(prin_memorie)
    assert streamed["Valoare"].tolist() == prin_memorie["Valoare"].tolist()


CSV_TOTAL = (
    "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
    "TOTAL, TOTAL, Anul 2024, Numar persoane, 4000.0\n"
)


def test_streaming_keeps_the_columns_of_the_whole_frame(monkeypatch, tmp_path):
    """Slices do not all carry the same derived columns.

    standardize adds a column only when it holds something, so the national
    total slice has no SIRUTA while the locality ones do. Written slice by
    slice, the CSV still has to end up with the columns, and the order, of the
    frame get() would have returned.
    """
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    def fake_post(payload, **kw):
        judet = payload["encQuery"].split(":")[0]
        return CSV_TOTAL if judet == "112" else CSV_FOM104D

    monkeypatch.setattr(client, "post_pivot", fake_post)
    prin_memorie = t.matrix("FOM104D").get(progress=False)
    assert "Localitati_siruta" in prin_memorie.columns

    cale = t.matrix("FOM104D").download(folder=tmp_path / "d",
                                        return_df=False, progress=False)
    streamed = pd.read_csv(cale, sep=";", encoding="utf-8-sig")
    assert list(streamed.columns) == list(prin_memorie.columns)
    assert len(streamed) == len(prin_memorie)
    assert streamed["Localitati_siruta"].isna().sum() == 1     # the TOTAL row


def test_return_df_false_needs_somewhere_to_write(monkeypatch):
    """With a temporary folder there is no path to hand back afterwards."""
    _setup(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("FOM104D").download(return_df=False, progress=False)
    assert "folder=" in str(info.value) and "out=" in str(info.value)


def test_without_a_folder_it_works_in_a_temporary_one(monkeypatch, tmp_path):
    _setup(monkeypatch)
    monkeypatch.setattr(incremental.tempfile, "gettempdir", lambda: str(tmp_path))

    df = t.matrix("FOM104D").download(progress=False)
    assert len(df) == 6
    # nothing left behind: no slices, no folder, no stray CSV
    assert not (tmp_path / "pytempo_FOM104D").exists()


def test_the_module_shortcut_matches_the_method(monkeypatch, tmp_path):
    _setup(monkeypatch)
    prin_metoda = t.matrix("FOM104D").download(folder=tmp_path / "a",
                                               progress=False)
    _setup(monkeypatch)
    prin_scurtatura = t.download("FOM104D", folder=tmp_path / "b",
                                 progress=False)
    pd.testing.assert_frame_equal(prin_scurtatura, prin_metoda)


# ----------------------------------------------------- selection, as in get

def test_download_takes_the_same_level_and_select(monkeypatch, tmp_path):
    cereri = _setup(monkeypatch)
    t.matrix("FOM104D").download(level="judet", select={"Ani": ["Anul 2023"]},
                                 folder=tmp_path / "d", progress=False)
    assert len(cereri) == 1
    blocuri = cereri[0]["encQuery"].split(":")
    assert blocuri[0] == "3064,3065"     # counties active
    assert blocuri[1] == "112"           # localities on their total
    assert blocuri[2] == "4247"          # only the selected year


def test_download_raw_skips_the_derived_columns(monkeypatch, tmp_path):
    _setup(monkeypatch)
    brut = t.matrix("FOM104D").download(folder=tmp_path / "d", raw=True,
                                        progress=False)
    assert not any(c.endswith("_nivel") for c in brut.columns)


# ------------------------------------------------------------------ resume

def _keep_slices(monkeypatch):
    """Stop the cleanup, so the slices stay for the next run to reuse.

    A complete download removes its own slices, which is right: they have been
    consolidated. Here we want to look at them, or to start the next run from
    them, as an interrupted download would.
    """
    monkeypatch.setattr(incremental, "_clean_up",
                        lambda paths, folder, temporary, destination: None)


def test_resume_asks_only_for_the_missing_slices(monkeypatch, tmp_path):
    folder = tmp_path / "d"
    cereri = _setup(monkeypatch)
    _keep_slices(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)
    assert len(cereri) == 3

    # rerun with the slices still on disk: nothing is asked for again
    cereri.clear()
    df = t.matrix("FOM104D").download(folder=folder, progress=False)
    assert cereri == []
    assert len(df) == 6              # rebuilt entirely from the checkpoint


def test_resume_refetches_exactly_what_was_deleted(monkeypatch, tmp_path):
    folder = tmp_path / "d"
    cereri = _setup(monkeypatch)
    _keep_slices(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)
    felii = sorted(p for p in folder.iterdir() if p.name.startswith("_chunk_"))
    assert len(felii) == 3

    # half of them go: only those come back over the wire
    felii[0].unlink()
    felii[2].unlink()
    cereri.clear()
    df = t.matrix("FOM104D").download(folder=folder, progress=False)
    assert len(cereri) == 2
    assert len(df) == 6                  # and the result is whole again


def test_resume_false_asks_for_everything_again(monkeypatch, tmp_path):
    folder = tmp_path / "d"
    cereri = _setup(monkeypatch)
    _keep_slices(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)

    cereri.clear()
    t.matrix("FOM104D").download(folder=folder, resume=False, progress=False)
    assert len(cereri) == 3


def test_a_different_selection_does_not_reuse_the_slices(monkeypatch, tmp_path):
    """The slice name carries the query, so it can only answer its own."""
    folder = tmp_path / "d"
    cereri = _setup(monkeypatch)
    _keep_slices(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)

    cereri.clear()
    t.matrix("FOM104D").download(folder=folder, level="judet", progress=False)
    assert len(cereri) == 1


# ------------------------------------------------------- a failing slice

def _flaky_post(monkeypatch, failing: set, csv_text=CSV_FOM104D):
    """post_pivot that fails on the requests whose index is in `failing`."""
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        if len(cereri) in failing:
            raise client.ServerUnavailable("the INS server did not answer")
        return csv_text

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return cereri


def test_one_failing_slice_does_not_sink_the_rest(monkeypatch, tmp_path,
                                                  capsys):
    folder = tmp_path / "d"
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    cereri = _flaky_post(monkeypatch, failing={2})

    df = t.matrix("FOM104D").download(folder=folder)
    assert len(cereri) == 3              # it carried on after the failure
    assert len(df) == 4                  # two requests of two rows each

    iesire = capsys.readouterr().out
    assert "1 slice(s) missing" in iesire
    assert "request 2" in iesire
    assert df.attrs["missing_requests"][0]["index"] == 2


def test_a_missing_slice_is_reported_even_when_quiet(monkeypatch, tmp_path,
                                                     capsys):
    """progress=False asks for silence about progress, not about a hole."""
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    _flaky_post(monkeypatch, failing={2})
    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)
    assert "1 slice(s) missing" in capsys.readouterr().out


def test_the_slices_are_kept_while_one_is_missing(monkeypatch, tmp_path):
    """The checkpoint survives a partial run: that is what resume needs."""
    folder = tmp_path / "d"
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    _flaky_post(monkeypatch, failing={2})
    t.matrix("FOM104D").download(folder=folder, progress=False)
    assert len(_slices(folder)) == 2

    # the second run asks only for the one that failed, and finishes the job
    cereri = _flaky_post(monkeypatch, failing=set())
    df = t.matrix("FOM104D").download(folder=folder, progress=False)
    assert len(cereri) == 1
    assert len(df) == 6
    assert _slices(folder) == []         # complete now, so cleaned up


def test_every_slice_failing_says_so(monkeypatch, tmp_path):
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    _flaky_post(monkeypatch, failing={1, 2, 3})
    with pytest.raises(ValueError) as info:
        t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)
    assert "nothing was downloaded" in str(info.value)


# ------------------------------------------------------- retry in the client

class _Response:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _no_waiting(monkeypatch):
    asteptari = []
    monkeypatch.setattr(client.time, "sleep", asteptari.append)
    return asteptari


def test_post_pivot_retries_a_read_timeout(monkeypatch):
    """Two timeouts then an answer is a success, not an error."""
    asteptari = _no_waiting(monkeypatch)
    incercari = []

    def fake_post(url, **kw):
        incercari.append(kw["timeout"])
        if len(incercari) < 3:
            raise requests.exceptions.ReadTimeout("Read timed out")
        return _Response(text="CSV")

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.post_pivot({"encQuery": "1"}) == "CSV"
    assert len(incercari) == 3
    assert incercari[0] == client.PIVOT_TIMEOUT == 60    # 30s was too short
    # the waits grow, they do not knock faster
    assert asteptari == [5, 15]


def test_post_pivot_retries_a_connection_error_and_a_5xx(monkeypatch):
    _no_waiting(monkeypatch)
    for cadere in (requests.ConnectionError("connection reset"), None):
        incercari = []

        def fake_post(url, _cadere=cadere, **kw):
            incercari.append(1)
            if len(incercari) < 2:
                if _cadere is not None:
                    raise _cadere
                return _Response(status_code=503)
            return _Response(text="CSV")

        monkeypatch.setattr(client.requests, "post", fake_post)
        assert client.post_pivot({"encQuery": "1"}) == "CSV"
        assert len(incercari) == 2


def test_post_pivot_gives_up_with_a_clear_message(monkeypatch):
    _no_waiting(monkeypatch)
    incercari = []

    def fake_post(url, **kw):
        incercari.append(1)
        raise requests.exceptions.ReadTimeout("Read timed out")

    monkeypatch.setattr(client.requests, "post", fake_post)
    with pytest.raises(client.ServerUnavailable) as info:
        client.post_pivot({"encQuery": "1"}, attempts=4)

    assert len(incercari) == 4
    mesaj = str(info.value)
    assert "INS server did not answer" in mesaj
    assert "Try again later" in mesaj
    assert "resume" in mesaj


def test_post_pivot_retries_an_empty_body(monkeypatch):
    """The POP108D case: 200 with zero bytes is rate limiting, not an answer.

    Measured in the field: 83 slices, the first 42 with data, then every one of
    the remaining 41 empty. Waiting clears it; writing them off does not.
    """
    asteptari = _no_waiting(monkeypatch)
    raspunsuri = ["", "   ", "Judete, Valoare\nAlba, 1\n"]

    def fake_post(url, **kw):
        return _Response(text=raspunsuri[len(asteptari)])

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.post_pivot({"encQuery": "1", "matCode": "POP108D"}) == \
        raspunsuri[2]
    # it waited the same growing waits as for a timeout, and then got data
    assert asteptari == [5, 15]


def test_an_empty_body_is_not_a_slice_without_data(monkeypatch):
    """A slice with no data comes back as a header with no rows, and is kept.

    That distinction is the whole reason an empty body can be retried safely:
    the two are not spelled the same way, so waiting for one never throws away
    the other.
    """
    _no_waiting(monkeypatch)
    doar_antet = "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
    incercari = []

    def fake_post(url, **kw):
        incercari.append(1)
        return _Response(text=doar_antet)

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.post_pivot({"encQuery": "1"}) == doar_antet
    assert len(incercari) == 1              # taken at face value, not retried


def test_an_empty_body_that_never_clears_is_reported(monkeypatch):
    """After the retries it is a failed slice, not an empty one.

    Accepting zero bytes as no data would punch a silent hole in the result,
    and pytempo does not read a missing figure as a zero anywhere else either.
    """
    _no_waiting(monkeypatch)
    incercari = []

    def fake_post(url, **kw):
        incercari.append(1)
        return _Response(text="")

    monkeypatch.setattr(client.requests, "post", fake_post)
    with pytest.raises(client.ServerUnavailable) as info:
        client.post_pivot({"encQuery": "1", "matCode": "POP108D"})

    assert len(incercari) == client.PIVOT_ATTEMPTS      # bounded, not a loop
    mesaj = str(info.value)
    assert "did not answer with data" in mesaj
    assert "EmptyResponse" in mesaj
    assert "POP108D" in mesaj
    assert "resume=True" in mesaj


def test_post_pivot_does_not_retry_a_bad_request(monkeypatch):
    """A 4xx is our own query and will not fix itself; failing fast is kinder."""
    _no_waiting(monkeypatch)
    incercari = []

    def fake_post(url, **kw):
        incercari.append(1)
        return _Response(status_code=400)

    monkeypatch.setattr(client.requests, "post", fake_post)
    with pytest.raises(requests.HTTPError):
        client.post_pivot({"encQuery": "1"})
    assert len(incercari) == 1


# --------------------------------------------------- pacing the requests

def _watch_sleeping(monkeypatch):
    """Record what download() waits, without waiting for it."""
    asteptari = []
    monkeypatch.setattr(incremental.time, "sleep", asteptari.append)
    return asteptari


def test_download_spaces_its_requests(monkeypatch, tmp_path):
    """Eighty three requests fired back to back is how the wall gets hit."""
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "REQUEST_SPACING", 0.5)
    asteptari = _watch_sleeping(monkeypatch)

    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)

    # three requests, so two gaps: nothing before the first, nothing after
    assert asteptari == [0.5, 0.5]


def test_the_spacing_can_be_turned_off(monkeypatch, tmp_path):
    """Zero for a small download, where politeness costs more than it buys."""
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "REQUEST_SPACING", 0)
    asteptari = _watch_sleeping(monkeypatch)

    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)
    assert asteptari == []


def test_a_skipped_slice_costs_no_wait(monkeypatch, tmp_path):
    """Resume reads from disk, and disk does not need to be asked politely."""
    folder = tmp_path / "d"
    _setup(monkeypatch)
    _keep_slices(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)

    monkeypatch.setattr(incremental, "REQUEST_SPACING", 0.5)
    asteptari = _watch_sleeping(monkeypatch)
    t.matrix("FOM104D").download(folder=folder, progress=False)
    assert asteptari == []


def test_the_spacing_grows_when_slices_keep_failing(monkeypatch, tmp_path,
                                                    capsys):
    """INS has had enough. Knocking harder is not an argument."""
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)
    monkeypatch.setattr(incremental, "REQUEST_SPACING", 0.5)
    asteptari = _watch_sleeping(monkeypatch)
    _flaky_post(monkeypatch, failing={1, 2})

    t.matrix("FOM104D").download(folder=tmp_path / "d", progress=False)

    # after the first failure 1s, after the second 2s
    assert asteptari == [1.0, 2.0]


def test_the_spacing_has_a_ceiling():
    """It slows down, it does not stop."""
    spacing = incremental.REQUEST_SPACING
    for _ in range(20):
        spacing = min(max(spacing * 2, 1.0), incremental.MAX_SPACING)
    assert spacing == incremental.MAX_SPACING == 8.0


def test_resume_finishes_what_rate_limiting_interrupted(monkeypatch, tmp_path):
    """The POP108D shape, in miniature: half the slices refused, then not.

    The first run keeps what it got and reports the rest; the second asks only
    for those and completes the file, with no intervention beyond running it
    again.
    """
    folder = tmp_path / "d"
    _api(monkeypatch, META)
    monkeypatch.setattr(chunking, "MAX_CELLS", 10)

    _flaky_post(monkeypatch, failing={2, 3})
    partial = t.matrix("FOM104D").download(folder=folder, progress=False)
    assert partial.attrs["complete"] is False
    assert len(partial) == 2
    assert len(_slices(folder)) == 1

    cereri = _flaky_post(monkeypatch, failing=set())
    whole = t.matrix("FOM104D").download(folder=folder, progress=False)
    assert len(cereri) == 2                  # only the two that were refused
    assert whole.attrs["complete"] is True
    assert len(whole) == 6


# ------------------------------------------------------- the slice format

def test_csv_slices_when_pyarrow_is_missing(monkeypatch, tmp_path):
    """The fallback is another slice format, not a hard dependency."""
    folder = tmp_path / "d"
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "slice_format", lambda: "csv")
    _keep_slices(monkeypatch)
    df = t.matrix("FOM104D").download(folder=folder, progress=False)

    assert all(name.endswith(".csv") for name in _slices(folder))
    assert len(df) == 6
    assert df["Localitati_siruta"].tolist()[:2] == [1017, 2130]


def test_parquet_slices_when_pyarrow_is_there(monkeypatch, tmp_path):
    pytest.importorskip("pyarrow")
    folder = tmp_path / "d"
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "slice_format", lambda: "parquet")
    _keep_slices(monkeypatch)
    df = t.matrix("FOM104D").download(folder=folder, progress=False)

    assert all(name.endswith(".parquet") for name in _slices(folder))
    pd.testing.assert_frame_equal(
        df, t.matrix("FOM104D").get(progress=False))


def test_both_slice_formats_give_the_same_frame(monkeypatch, tmp_path):
    pytest.importorskip("pyarrow")
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "slice_format", lambda: "csv")
    prin_csv = t.matrix("FOM104D").download(folder=tmp_path / "c",
                                            progress=False)
    _setup(monkeypatch)
    monkeypatch.setattr(incremental, "slice_format", lambda: "parquet")
    prin_parquet = t.matrix("FOM104D").download(folder=tmp_path / "p",
                                                progress=False)
    pd.testing.assert_frame_equal(prin_csv, prin_parquet, check_dtype=False)


def test_slice_names_are_deterministic(monkeypatch, tmp_path):
    """Same request, same file. That is what makes resume safe."""
    payload = {"encQuery": "3064:113,114:4247:9685"}
    intai = incremental.slice_path(tmp_path, 2, payload, "csv")
    din_nou = incremental.slice_path(tmp_path, 2, payload, "csv")
    altul = incremental.slice_path(tmp_path, 2, {"encQuery": "3065:116"}, "csv")
    assert intai == din_nou
    assert intai != altul
    assert intai.name.startswith("_chunk_0002_")


# ------------------------------------------------------------- regression

def test_get_on_a_small_matrix_is_untouched(monkeypatch):
    """The small path has to be exactly what it was: one request, same frame."""
    cereri = _setup(monkeypatch, chunked=False)
    df = t.matrix("SOM101B").get(level="judet", progress=False)

    assert len(cereri) == 1
    assert cereri[0] == {
        "language": "ro", "encQuery": "4,5:20:30", "matCode": "SOM101B",
        "matMaxDim": 5, "matUMSpec": None}
    assert list(df.columns) == [
        "Macroregiuni, regiuni de dezvoltare si judete", "Ani",
        "UM: Numar persoane", "Valoare",
        "Macroregiuni, regiuni de dezvoltare si judete_nivel", "Ani_an"]
    assert df["Valoare"].tolist() == [12.5, 18.0]
    assert list(df.index) == [0, 1]
