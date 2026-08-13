"""A pandas accessor for the tidy frames get() returns: df.tempo.

Registered on import, so `import pytempo` is enough to make `df.tempo` work on
any frame produced by get(tidy=True). It reshapes and summarizes; it never
fetches anything and never mutates the frame it is given.

The accessor recognizes its own output by the derived columns standardize adds:
a frame with no <label>_nivel and no <label>_an column is not tidy output, and
every method says so rather than guessing.
"""
import pandas as pd

from .parse import VALUE_COLUMN

NOT_TIDY = ("this DataFrame does not look like pytempo tidy output; "
            "use m.get() (tidy is on by default)")

# suffixes standardize appends; these are never part of a reshaping index
_DERIVED_SUFFIXES = ("_siruta", "_nivel", "_tip", "_nume", "_an")


def _derived(column: str) -> bool:
    return any(column.endswith(s) for s in _DERIVED_SUFFIXES)


def _base_of(column: str, suffix: str) -> str:
    return column[:-len(suffix)]


@pd.api.extensions.register_dataframe_accessor("tempo")
class TempoAccessor:
    """Reshaping and reporting on a tidy pytempo frame."""

    def __init__(self, df):
        self._df = df
        self._year_col = next(
            (c for c in df.columns if c.endswith("_an")), None)
        self._level_col = next(
            (c for c in df.columns if c.endswith("_nivel")), None)
        self._is_tidy = self._year_col is not None or self._level_col is not None

    def _check(self) -> None:
        if not self._is_tidy:
            raise ValueError(NOT_TIDY)

    def _index_columns(self) -> list[str]:
        """The original dimension columns that make a row unique in a wide table.

        Left out: the derived columns, the value, the original time column
        (its year column says the same thing), and a unit of measure column
        that never varies, which would only pad the index.
        """
        df = self._df
        time_base = (_base_of(self._year_col, "_an") if self._year_col else None)
        keep = []
        for column in df.columns:
            if column == VALUE_COLUMN or _derived(column):
                continue
            if column == time_base:
                continue
            if column.strip().upper().startswith("UM:") and \
                    df[column].nunique(dropna=False) <= 1:
                continue
            keep.append(column)
        return keep

    def wide(self, values: str = VALUE_COLUMN) -> pd.DataFrame:
        """Pivot time into columns: one column per year.

        The index is built from the original dimension columns, so the result
        reads like a table you would put in a paper. Returns a new frame.
        """
        self._check()
        if self._year_col is None:
            raise ValueError(
                "no year column found, so there is nothing to pivot on; "
                "a tidy frame from a time series has a <label>_an column")
        if values not in self._df.columns:
            raise ValueError(f"column {values!r} is not in this DataFrame")

        index = self._index_columns()
        if not index:
            raise ValueError(
                "nothing left to index by once time, value and derived "
                "columns are removed")
        try:
            wide = self._df.pivot(index=index, columns=self._year_col,
                                  values=values)
        except ValueError as exc:
            raise ValueError(
                f"cannot pivot: the rows are not unique per year and "
                f"{index}. The original error was: {exc}") from None
        wide.columns.name = None
        return wide.reset_index()

    def coverage(self) -> pd.DataFrame:
        """What each territorial unit actually covers, and where the holes are.

        One row per unit: the first and last year it has, how many years, how
        many of the years seen anywhere in the frame are missing for it, and
        the smallest and largest value with the year each occurred.

        When the frame mixes territorial levels, the level comes first, so a
        national total is never read as if it were a county.
        """
        self._check()
        if self._year_col is None:
            raise ValueError(
                "no year column found, so coverage cannot be computed")

        df = self._df
        name_col = next((c for c in df.columns if c.endswith("_nume")), None)
        if name_col is None and self._level_col is not None:
            name_col = _base_of(self._level_col, "_nivel")

        grouping = []
        mixed_levels = (self._level_col is not None
                        and df[self._level_col].nunique(dropna=False) > 1)
        if mixed_levels:
            grouping.append(self._level_col)
        if name_col is not None and name_col in df.columns:
            grouping.append(name_col)

        all_years = set(df[self._year_col].dropna().tolist())

        rows = []
        groups = df.groupby(grouping, dropna=False) if grouping else \
            [((), df)]
        for key, part in groups:
            years = set(part[self._year_col].dropna().tolist())
            valid = part.dropna(subset=[VALUE_COLUMN])
            row = {}
            if grouping:
                key = key if isinstance(key, tuple) else (key,)
                for column, value in zip(grouping, key):
                    row[column] = value
            else:
                row["unit"] = "(all)"
            row["first_year"] = min(years) if years else pd.NA
            row["last_year"] = max(years) if years else pd.NA
            row["n_years"] = len(years)
            row["missing_years"] = len(all_years - years)
            if len(valid):
                low = valid.loc[valid[VALUE_COLUMN].idxmin()]
                high = valid.loc[valid[VALUE_COLUMN].idxmax()]
                row["min_value"] = low[VALUE_COLUMN]
                row["min_year"] = low[self._year_col]
                row["max_value"] = high[VALUE_COLUMN]
                row["max_year"] = high[self._year_col]
            else:
                for field in ("min_value", "min_year", "max_value", "max_year"):
                    row[field] = pd.NA
            rows.append(row)

        return pd.DataFrame(rows)

    def geo(self):
        """Join the rows to UAT geometries on SIRUTA. NOT IMPLEMENTED.

        The intent, so it is readable before it exists: take the <label>_siruta
        column, join it to the official administrative unit geometries, and
        return a GeoDataFrame ready to plot or to write to PostGIS. Rows whose
        SIRUTA is missing, which is every aggregate above locality level, would
        be reported rather than silently dropped.

        It is not here yet because it needs geopandas and a geometry source,
        and pytempo keeps its dependency list at requests and pandas. It will
        arrive as an optional extra, installed with pytempo[geo], so that
        anyone who only wants the numbers never pays for the geometry stack.
        """
        raise NotImplementedError(
            "geo() is not implemented yet: it will join on SIRUTA and return "
            "a GeoDataFrame, arriving as the optional pytempo[geo] extra")
