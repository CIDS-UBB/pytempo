"""Generating a Postgres schema straight from an indicator's metadata.

A PURE metadata function: it opens no connection and imports no driver. It
produces the schema a downstream project would use to load the data.

The model: one table per indicator, one column per dimension plus the value
column. Types are inferred from the dimension role:
    time (year)    -> INTEGER
    value          -> NUMERIC / DOUBLE PRECISION
    territory, sex, caen, unit, other -> TEXT
Plus columns for the territorial level and the territorial code.
The INS definition and methodology become COMMENT ON TABLE and COMMENT ON
COLUMN, so the meaning of every column travels with the schema.
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
        """Serialize the schema as DDL (CREATE TABLE plus COMMENT ON ...).

        dialect: 'postgres' (the default) or 'sqlite'.
        """
        raise NotImplementedError("not implemented yet")


def build_schema(matrix, dialect: str = "postgres") -> Schema:
    """Build a Schema from a matrix's metadata. See the module description."""
    raise NotImplementedError("not implemented yet")
