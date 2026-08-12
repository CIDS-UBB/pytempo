"""Toate URL-urile TEMPO, într-un singur loc. Sursă unică de adevăr pentru căi.

BASE_URL e suprascriptibil din variabila de mediu TEMPO_BASE_URL. INS folosește un
port ne-standard (8077); dacă se schimbă vreodată gazda sau portul, se modifică aici
o singură linie, nu prin tot codul. Nu hardcoda niciun URL altundeva.
"""
import os

BASE_URL = os.environ.get(
    "TEMPO_BASE_URL",
    "http://statistici.insse.ro:8077/tempo-ins/",
)

# endpoint-ul separat de config al aplicației web (poate conține limite)
CONFIG_URL = os.environ.get(
    "TEMPO_CONFIG_URL",
    "http://statistici.insse.ro:8077/tempo-online/assets/data/tempo-config.json",
)


def context(code: str = "") -> str:
    """Arborele de domenii statistice. Rădăcina (code='') dă A/B/C/D."""
    return f"{BASE_URL}context/{code}"


def matrices(lang: str = "ro") -> str:
    """Indexul tuturor matricelor: cod + nume. Baza pentru search."""
    return f"{BASE_URL}matrix/matrices?lang={lang}"


def matrix(cod: str) -> str:
    """Metadatele unei matrice (dimensiuni, opțiuni, definiție, metodologie)."""
    return f"{BASE_URL}matrix/{cod}"


def pivot() -> str:
    """Endpoint de date (POST, întoarce CSV)."""
    return f"{BASE_URL}pivot"


def dataset() -> str:
    """Endpoint de date alternativ (JSON). pivot e calea probată."""
    return f"{BASE_URL}matrix/dataSet/"
