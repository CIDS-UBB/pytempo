"""Shared setup for the test suite.

The download path now waits between requests, which is right against the real
server and pointless here: the suite would spend minutes asleep to prove
nothing. Tests check the spacing by watching the calls, not by living through
them, so the wait is off everywhere by default and switched on deliberately in
the few tests that are about it.
"""
import pytest

from pytempo import incremental


@pytest.fixture(autouse=True)
def no_polite_waiting(monkeypatch):
    monkeypatch.setattr(incremental, "REQUEST_SPACING", 0)
