"""Generarea schemei Postgres direct din metadatele unui indicator.

Funcție PURĂ de metadate: nu deschide nicio conexiune, nu importă niciun driver.
Produce schema pe care ar folosi-o un proiect din aval ca să încarce datele.

Model: un tabel per indicator, o coloană per dimensiune plus coloana valoare.
Tipuri inferate din rolul dimensiunii:
    timp (an)      -> INTEGER
    valoare        -> NUMERIC / DOUBLE PRECISION
    teritoriu, sex, caen, um, alt -> TEXT
Plus coloane pentru nivelul teritorial și codul teritorial.
Definiția și metodologia INS devin COMMENT ON TABLE / COMMENT ON COLUMN, ca sensul
fiecărei coloane să călătorească odată cu schema.
"""
from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type: str
    source_dimension: str = ""
    comment: str = ""


@dataclass
class Schema:
    table: str
    columns: list[Column] = field(default_factory=list)
    table_comment: str = ""

    def to_ddl(self, dialect: str = "postgres") -> str:
        """Serializează schema ca DDL (CREATE TABLE + COMMENT ON ...).

        dialect: 'postgres' (implicit) sau 'sqlite'.
        """
        raise NotImplementedError("iterația 5")


def build_schema(matrix, dialect: str = "postgres") -> Schema:
    """Construiește Schema din metadatele unei matrice. Vezi descrierea modulului."""
    raise NotImplementedError("iterația 5")
