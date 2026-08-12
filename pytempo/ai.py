"""VIITOR (opțional): descoperire în limbaj natural. Mod AI.

Idee: 'vreau statistici despre șomeri' -> o listă de indicatori candidați, prin
potrivirea cererii peste indexul de matrice cu ajutorul unui model.

Izolat aici intenționat, ca nucleul să NU capete dependințe AI. Off by default.
Modelul (Anthropic API sau unul local) e configurabil, nu impus.
"""


def discover(query: str, client=None, limit: int = 10) -> list:
    """Întoarce indicatori candidați pentru o cerere în limbaj natural.

    Neimplementat: seam pentru viitor. Nucleul funcționează complet fără el.
    """
    raise NotImplementedError("viitor, opțional: mod AI")
