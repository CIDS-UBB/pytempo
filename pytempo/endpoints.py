"""Every TEMPO URL in one place. The single source of truth for paths.

BASE_URL can be overridden through the TEMPO_BASE_URL environment variable. INS
runs on a non standard port (8077); if the host or the port ever changes, one
line here changes with it, not code scattered around. Do not hardcode a URL
anywhere else.
"""
import os

BASE_URL = os.environ.get(
    "TEMPO_BASE_URL",
    "http://statistici.insse.ro:8077/tempo-ins/",
)

# the web application's separate config endpoint (it may carry limits)
CONFIG_URL = os.environ.get(
    "TEMPO_CONFIG_URL",
    "http://statistici.insse.ro:8077/tempo-online/assets/data/tempo-config.json",
)


def context(code: str = "") -> str:
    """The tree of statistical domains. The root (code='') gives A through H."""
    return f"{BASE_URL}context/{code}"


def matrices(lang: str = "ro") -> str:
    """The index of every matrix: code plus name. What search is built on."""
    return f"{BASE_URL}matrix/matrices?lang={lang}"


def matrix(cod: str) -> str:
    """One matrix's metadata (dimensions, options, definition, methodology)."""
    return f"{BASE_URL}matrix/{cod}"


def pivot() -> str:
    """The data endpoint (POST, returns CSV)."""
    return f"{BASE_URL}pivot"


def dataset() -> str:
    """Alternative data endpoint (JSON). pivot is the proven path."""
    return f"{BASE_URL}matrix/dataSet/"
