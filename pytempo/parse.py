"""Transformă CSV-ul de la pivot în DataFrame, format lung.

Format măsurat pe răspunsul real (FOM101A): delimitator virgulă, cu un spațiu
după fiecare câmp, zecimala punct, fără ghilimele nicăieri, terminator \\n,
utf-8 fără BOM. O coloană per dimensiune, în ordinea din dimensionsMap, plus
coloana Valoare la final.

Două capcane, amândouă confirmate pe date reale:

Antetul nu e de încredere ca sursă de nume. INS înlocuiește virgulele din
denumirea dimensiunii cu spații, deci 'Macroregiuni, regiuni de dezvoltare si
judete' ajunge 'Macroregiuni  regiuni de dezvoltare si judete'. Luăm numele din
matrix.dimensions, în ordine, nu din antet.

CSV-ul e rar. Combinațiile fără date lipsesc ca rânduri întregi, nu ca valori
goale, din motive administrative reale (Ilfov nu exista înainte de 1996). Nu
validăm pe numărul de rânduri și nu presupunem un grid complet.
"""
import io
import re

import pandas as pd

from . import territory

VALUE_COLUMN = "Valoare"

_YEAR = re.compile(r"\b(\d{4})\b")


def pivot_csv_to_dataframe(csv_text: str, matrix) -> pd.DataFrame:
    """CSV brut de la pivot -> DataFrame în format lung.

    Numărul de coloane e plasa de siguranță: delimitatorul virgulă ține doar
    fiindcă INS curăță virgulele din denumiri, iar asta nu e garantat.
    """
    df = pd.read_csv(
        io.StringIO(csv_text),
        sep=",",
        skipinitialspace=True,
        decimal=".",
    )

    asteptat = len(matrix.dimensions) + 1
    if df.shape[1] != asteptat:
        raise ValueError(
            f"CSV cu {df.shape[1]} coloane, asteptate {asteptat} "
            f"({len(matrix.dimensions)} dimensiuni plus {VALUE_COLUMN}). "
            f"Antet gasit: {list(df.columns)}"
        )

    df.columns = [d.label.strip() for d in matrix.dimensions] + [VALUE_COLUMN]

    if df.empty:
        # un raspuns fara randuri e legitim: combinatia ceruta nu are date.
        # Coloana goala nu are dtype de citit, deci o fixam noi in loc sa
        # confundam golul cu o mapare gresita de coloane.
        df[VALUE_COLUMN] = df[VALUE_COLUMN].astype("float64")
    elif not pd.api.types.is_numeric_dtype(df[VALUE_COLUMN]):
        raise ValueError(
            f"Coloana {VALUE_COLUMN} nu e numerica (dtype "
            f"{df[VALUE_COLUMN].dtype}). Semn ca maparea coloanelor a alunecat."
        )
    return df


def _year_of(label) -> int | None:
    """Anul dintr-o denumire de perioadă: 'Anul 2024' -> 2024."""
    m = _YEAR.search(str(label))
    return int(m.group(1)) if m else None


def standardize(df: pd.DataFrame, matrix) -> pd.DataFrame:
    """Adaugă coloane derivate, fără să șteargă sau să rearanjeze nimic.

    Pentru fiecare dimensiune teritorială adaugă <label>_siruta, <label>_nivel,
    <label>_tip și <label>_nume. Pentru fiecare dimensiune de timp adaugă
    <label>_an. Prefixul e labelul dimensiunii, ca să nu se ciocnească atunci
    când matricea are două dimensiuni teritoriale (FOM104D).

    SIRUTA e cheie, deci se adaugă ca o coloană nouă; denumirea originală
    rămâne intactă, cu prefixul ei cu tot.
    """
    out = df.copy()
    for dim in matrix.dimensions:
        col = dim.label.strip()
        if col not in out.columns:
            continue

        if dim.role == "teritoriu":
            desfacut = [territory.parse_territory(v) for v in out[col]]
            out[f"{col}_siruta"] = pd.array(
                [t[0] for t in desfacut], dtype="Int64")
            # string nullable: tip lipseste la agregate si judete, iar acolo
            # vrem pd.NA, nu NaN de float
            out[f"{col}_nivel"] = pd.array(
                [t[1] for t in desfacut], dtype="string")
            out[f"{col}_tip"] = pd.array(
                [t[2] for t in desfacut], dtype="string")
            out[f"{col}_nume"] = pd.array(
                [t[3] for t in desfacut], dtype="string")

        elif dim.role == "timp":
            out[f"{col}_an"] = pd.array(
                [_year_of(v) for v in out[col]], dtype="Int64")
    return out
