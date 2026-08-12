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

import pandas as pd

VALUE_COLUMN = "Valoare"


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

    if not pd.api.types.is_numeric_dtype(df[VALUE_COLUMN]):
        raise ValueError(
            f"Coloana {VALUE_COLUMN} nu e numerica (dtype "
            f"{df[VALUE_COLUMN].dtype}). Semn ca maparea coloanelor a alunecat."
        )
    return df
