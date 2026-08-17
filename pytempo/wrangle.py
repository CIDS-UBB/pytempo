"""A pandas accessor for the tidy frames get() returns: df.tempo.

Registered on import, so `import pytempo` is enough to make `df.tempo` work on
any frame produced by get(tidy=True). It reshapes and summarizes; it never
fetches anything and never mutates the frame it is given.

The accessor recognizes its own output by the derived columns standardize adds:
a frame with no <label>_nivel and no <label>_an column is not tidy output, and
every method says so rather than guessing.
"""
import pandas as pd

from . import spotcheck
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

    def _territorial_bases(self) -> list[str]:
        """The base names of the territorial dimensions, from their level column."""
        return [_base_of(c, "_nivel") for c in self._df.columns
                if c.endswith("_nivel")]

    def _unit_base(self) -> str | None:
        """The territorial dimension holding the real units.

        The one carrying SIRUTA when there is one, since that is where the
        localities are, otherwise the first territorial dimension.
        """
        bases = self._territorial_bases()
        with_siruta = next(
            (b for b in bases if f"{b}_siruta" in self._df.columns), None)
        return with_siruta or (bases[0] if bases else None)

    def _inner_columns(self, unit_base: str | None) -> list[str]:
        """The dimensions that are neither territory, nor time, nor the unit.

        What is left is what a spot check has to pin: sex, age group, level of
        education, form of ownership. A unit of measure column counts too when
        it varies, since two units of measure are two series.
        """
        df = self._df
        time_base = _base_of(self._year_col, "_an") if self._year_col else None
        territorial = set(self._territorial_bases())
        keep = []
        for column in df.columns:
            if column == VALUE_COLUMN or _derived(column):
                continue
            if column in territorial or column == time_base:
                continue
            if column.strip().upper().startswith("UM:") and \
                    df[column].nunique(dropna=False) <= 1:
                continue
            keep.append(column)
        return keep

    def spot_check(self, n: int = 1, seed=None) -> None:
        """Pick n units at random and print how to check them on the site.

        The one kind of error no internal check can catch is a number that is
        correct and means something else. This does not verify anything by
        itself; it prepares the manual comparison, which is the only real
        verification there is.

        For each unit picked it prints the name, the county and the SIRUTA,
        pins every other dimension on its total so the site shows a single
        series, says what it pinned and on what, and prints the series year by
        year, ready to read against the screen. A dimension with no total gets
        its first option and is named as such.

        seed makes the choice reproducible. Nothing here touches the network:
        it reads the frame you already downloaded.

            df.tempo.spot_check(2, seed=7)
        """
        self._check()
        if self._year_col is None:
            raise ValueError(
                "no year column found, so there is no series to check; "
                "a tidy frame from a time series has a <label>_an column")

        unit_base = self._unit_base()
        if unit_base is None:
            raise ValueError(
                "no territorial dimension in this frame, so there is no unit "
                "to look up on the site")

        context = [b for b in self._territorial_bases() if b != unit_base]
        spotcheck.report(self._df, self._unit_key(unit_base), unit_base,
                         self._year_col, self._inner_columns(unit_base),
                         context, n=n, seed=seed)

    def _unit_key(self, base: str) -> pd.Series:
        """The grouping key for one territorial dimension.

        SIRUTA is the key, the name is only a label: locality names are not
        unique in Romania, and grouping by name silently merges communes that
        share a name across counties, mixing their series into one. Rows with
        no SIRUTA, which is every aggregate, fall back to the original label,
        which still carries the code when there is one.
        """
        df = self._df
        siruta = f"{base}_siruta"
        labels = df[base].astype("string")
        if siruta in df.columns:
            return df[siruta].astype("string").fillna(labels)
        return labels

    def coverage(self) -> pd.DataFrame:
        """What each territorial unit actually covers, and where the holes are.

        One row per unit: the first and last year it has, how many years, how
        many of the years seen anywhere in the frame are missing for it, and
        the smallest and largest value with the year each occurred.

        Units are keyed by SIRUTA when the frame carries it, never by name.
        The name and, where a second territorial dimension exists, the county
        are shown as labels, so two communes with the same name stay two rows
        and can be told apart by eye as well as by code.

        When the frame mixes territorial levels, the level of the dimension
        being grouped comes first, so an aggregate is never read as a unit.
        """
        self._check()
        if self._year_col is None:
            raise ValueError(
                "no year column found, so coverage cannot be computed")

        df = self._df
        bases = self._territorial_bases()
        # the dimension carrying SIRUTA is the one with real units in it
        unit = self._unit_base()

        all_years = set(df[self._year_col].dropna().tolist())

        if unit is None:
            parts = [("(all)", df)]
            label_cols = []
        else:
            key = self._unit_key(unit)
            parts = list(df.groupby(key, dropna=False, sort=False))
            level_col = f"{unit}_nivel"
            name_col = f"{unit}_nume" if f"{unit}_nume" in df.columns else unit
            # a second territorial dimension is context: it tells two
            # same named communes apart
            context = [b for b in bases if b != unit]
            label_cols = []
            if df[level_col].nunique(dropna=False) > 1:
                label_cols.append(level_col)
            label_cols += context
            label_cols.append(name_col)
            if f"{unit}_siruta" in df.columns:
                label_cols.append(f"{unit}_siruta")

        rows = []
        for _, part in parts:
            years = set(part[self._year_col].dropna().tolist())
            valid = part.dropna(subset=[VALUE_COLUMN])
            row = {}
            if unit is None:
                row["unit"] = "(all)"
            else:
                first = part.iloc[0]
                for column in label_cols:
                    row[column] = first[column]
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
