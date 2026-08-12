"""Descoperire: navigarea arborelui de context și exploratorul interactiv.

Motorul real e browse() + catalog.search(); init() e doar UI-ul deasupra lor.
UI-ul interactiv (meniu în terminal / notebook) e o iterație viitoare; funcțiile
de dedesubt sunt cele care contează.
"""
from . import endpoints, client, catalog


def browse(code: str = "") -> list:
    """Navighează arborele de context TEMPO.

    code='' întoarce domeniile de sus (A. Statistica socială, B. Statistica
    economică, C. Finanțe, D. Justiție ...). Un cod de nod întoarce copiii lui.
    Coborâre pas cu pas până la indicatori.
    """
    raise NotImplementedError("iterația 4")


def init() -> None:
    """Explorator interactiv, ca să te joci cu datele.

    Pornește de la domeniile A/B/C/D, te lasă să cobori, să cauți (inclusiv fuzzy),
    să filtrezi pe nivel, să alegi un indicator și să-i vezi info + nivele. Rulează
    în terminal sau notebook. UI-ul e viitor; se sprijină pe browse() și search().
    """
    raise NotImplementedError("iterația 4")
