"""Offline tests for finding out that download() exists, and when to use it.

download() worked before anyone could learn about it: it was in no help text,
and how(), the manual for one indicator, mentioned it in a footnote under a
list of get() calls that would not run. A feature nobody can find is not a
feature, so what is tested here is the telling.
"""
import sys

import pytest

import pytempo as t
from pytempo import chunking

from .test_guidance import _api, _post, _registry
from .test_scale import _matrix as _pop107d
from .test_smoke import FOM104D_MIC

CSV = {"SOM101B": ("Macroregiuni  regiuni de dezvoltare si judete, Ani, "
                   "UM: Numar persoane, Valoare\n"
                   "Bihor, Anul 2020, Numar persoane, 12.5\n")}


def _how(m, capsys) -> str:
    m.how()
    return capsys.readouterr().out


# --------------------------------------------------- how() on a large one

def test_how_on_a_large_indicator_sends_you_to_download(monkeypatch, capsys):
    """POP107D at locality level is 380 requests. get() will not run it."""
    _pop107d(monkeypatch)
    out = _how(t.matrix("POP107D"), capsys)

    assert "THIS ONE IS LARGE: 380 requests" in out
    # the command carries this indicator's level and its own folder, so it
    # runs as printed rather than after being edited
    assert "m.download(level='localitate', folder='data/pop107d')" in out
    # and what download() does that get() does not
    assert "checkpoint" in out and "resume" in out
    assert "retries when INS times out" in out


def test_the_warning_comes_before_the_get_lines(monkeypatch, capsys):
    """At the bottom it was a footnote to scroll to. It belongs first."""
    _pop107d(monkeypatch)
    out = _how(t.matrix("POP107D"), capsys)

    assert out.index("THIS ONE IS LARGE") < out.index("df = m.get()")
    # in the first third of the printout, not at the end
    assert out.index("THIS ONE IS LARGE") < len(out) / 3


def test_how_counts_what_get_would_really_send(monkeypatch, capsys):
    """The registry estimates one request per county, 43. There are 380.

    A manual that promises a number get() then refuses is worse than none, so
    how() plans the download instead of trusting the estimate.
    """
    _pop107d(monkeypatch)
    m = t.matrix("POP107D")
    assert m.fetch_plan().get("est_requests") in (None, 43)

    out = _how(m, capsys)
    assert "strategy: by_county, 380 requests" in out
    assert m._request_count(m.fetch_plan()) == 380


def test_how_points_at_select_when_a_dimension_is_big(monkeypatch, capsys):
    """104 ages: the cheaper answer is often to ask for fewer of them."""
    _pop107d(monkeypatch)
    out = _how(t.matrix("POP107D"), capsys)

    assert "large dimensions: Varste si grupe de varsta (104 options)" in out
    assert "take only part of one with select=" in out
    assert "m.options('Varste si grupe de varsta')" in out
    # the territorial dimensions are not listed there: level= is their tool
    assert "Localitati (3182 options)" not in out


# --------------------------------------------------- how() on a small one

def test_how_on_a_small_indicator_does_not_scare(monkeypatch, tmp_path,
                                                 capsys):
    _registry(monkeypatch, tmp_path)
    out = _how(t.matrix("SOM101B"), capsys)

    assert "THIS ONE IS LARGE" not in out
    assert "stops and sends you here" not in out
    # get() stays the answer, and comes first
    assert "df = m.get()" in out


def test_how_on_a_small_indicator_still_mentions_download(monkeypatch,
                                                          tmp_path, capsys):
    """Available, not required: someone may want the CSV rather than a frame."""
    _registry(monkeypatch, tmp_path)
    out = _how(t.matrix("SOM101B"), capsys)

    assert "m.download(folder='data/som101b')" in out
    assert "written straight to a CSV on disk" in out


def test_a_small_indicator_gets_no_select_hint(monkeypatch, tmp_path, capsys):
    """SOM101B has nothing big enough to be worth trimming."""
    _registry(monkeypatch, tmp_path)
    out = _how(t.matrix("SOM101B"), capsys)
    assert "large dimensions:" not in out


# ------------------------------------------------------- the gate message

def test_the_gate_names_the_indicator_and_the_command(monkeypatch):
    _pop107d(monkeypatch)
    with pytest.raises(ValueError) as info:
        t.matrix("POP107D").get(progress=False)
    message = str(info.value)

    assert message.startswith("POP107D is large: 380 requests")
    assert "over the 50" in message
    assert "Nothing has been downloaded yet" in message
    # why not get(), what to run instead, and where the manual is
    assert "keeps every request in memory" in message
    assert "m.download(folder='data/pop107d')" in message
    assert "See m.how() for the whole manual" in message
    assert "get(confirm=False)" in message


def test_the_command_follows_the_level_that_was_asked_for(monkeypatch):
    """Suggesting a level the caller did not ask for would be a different
    download from the one they wanted."""
    _pop107d(monkeypatch)
    monkeypatch.setattr(chunking, "MAX_CELLS", 100)
    with pytest.raises(ValueError) as info:
        t.matrix("POP107D").get(level="judet", progress=False)
    assert "m.download(level='judet', folder='data/pop107d')" in str(info.value)


def test_the_gate_still_lets_confirm_false_through(monkeypatch, tmp_path):
    """Regression: the way out has not moved."""
    _registry(monkeypatch, tmp_path, {"FOM104D": FOM104D_MIC})
    monkeypatch.setattr(chunking, "MAX_CELLS", 2)
    monkeypatch.setattr(sys.modules["pytempo.matrix"], "POLITE_REQUESTS", 2)
    cereri = _post(monkeypatch, {"FOM104D": (
        "Judete, Localitati, Ani, UM: Numar persoane, Valoare\n"
        "Alba, 1017 MUNICIPIUL ALBA IULIA, Anul 2024, Numar persoane, 1\n")})

    t.matrix("FOM104D").get(progress=False, confirm=False)
    assert len(cereri) > 2


# ------------------------------------------------------- the help screens

def test_the_package_guide_mentions_download(capsys):
    t.help()
    out = capsys.readouterr().out

    assert "m.download(folder='data/x')" in out
    assert "t.download(" in out
    # and says which of the two to reach for
    assert "Which of the two" in out
    assert "m.how() prints the answer" in out


def test_the_indicator_guide_mentions_download(monkeypatch, capsys):
    _api(monkeypatch)
    t.matrix("SOM101B").help()
    out = capsys.readouterr().out

    assert ".download(folder='data/x')" in out
    assert "checkpointed" in out and "resumable" in out
    assert ".how()" in out


def test_every_guide_names_download(monkeypatch, tmp_path, capsys):
    """Whatever a reader opens first, download() is in it."""
    _registry(monkeypatch, tmp_path)
    m = t.matrix("SOM101B")

    for guide in (t.help, m.help, m.how):
        guide()
        assert "download" in capsys.readouterr().out, guide.__name__
