"""Downloading a large indicator piece by piece, with a checkpoint on disk.

get() keeps every frame in memory until the last request comes back. That is
right for the vast majority of indicators and wrong for the few big ones:
SAN101B, 36 categories by 3 properties by 3177 localities by 31 years, is a plan
of 130 requests, and a single late failure loses the lot with nothing to resume
from. Measured: five hours and abandoned through get(), under three minutes when
each county was written to disk as it arrived.

So this module writes each request's result to its own slice file the moment it
arrives, and only at the end reads the slices back, concatenates them, tidies
and writes one CSV. Memory stays at one slice, an interrupted run keeps what it
had, and a rerun with resume=True asks only for what is missing.

Slices are Parquet when pyarrow is installed and CSV otherwise. pyarrow is
faster and keeps dtypes, but the core stays on requests and pandas alone, so it
is an optional extra rather than a dependency.

Nothing here plans or selects: it receives the payloads that chunking.
plan_requests built and executes them. The planning lives in Matrix, shared with
get(), so both go through exactly the same selection.
"""
import hashlib
import importlib.util
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from . import client, parse

# the conventions for the consolidated CSV: Excel in Romania reads ';' as the
# separator, and the BOM is what makes it show diacritics without being asked
CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig"

# the derived columns parse.standardize can add, in the order it adds them.
# Needed only to rebuild that order when consolidating slice by slice, without
# ever holding the whole frame
_DERIVED = ("_siruta", "_nivel", "_tip", "_nume", "_an")


def slice_format() -> str:
    """'parquet' when pyarrow is there, 'csv' otherwise. Same mechanism."""
    return "parquet" if importlib.util.find_spec("pyarrow") else "csv"


def slice_path(folder: Path, index: int, payload: dict, fmt: str) -> Path:
    """Where the result of one request lives, named after what it asked for.

    The index keeps the plan's order readable on disk; the hash of the encQuery
    ties the file to its content. Change the selection and the names change, so
    resume can never hand back a slice that answers a different question.
    """
    key = hashlib.sha1(payload["encQuery"].encode("utf-8")).hexdigest()[:8]
    return Path(folder) / f"_chunk_{index:04d}_{key}.{fmt}"


def _write_slice(df: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, sep=CSV_SEP, index=False, encoding="utf-8")


def _read_slice(path: Path, matrix) -> pd.DataFrame:
    """One slice back into a frame, with the dimension columns kept as text.

    A CSV slice has no dtypes of its own, and a dimension whose labels are all
    digits would come back as numbers. The names are taken from the matrix, as
    everywhere else in the package.
    """
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    labels = {d.label.strip(): str for d in matrix.dimensions}
    return pd.read_csv(path, sep=CSV_SEP, encoding="utf-8", dtype=labels)


def _tidied(df: pd.DataFrame, matrix, tidy: bool, raw: bool) -> pd.DataFrame:
    """The same last step get() takes, so the two agree column for column."""
    return df if raw or not tidy else parse.standardize(df, matrix)


def _ordered_columns(matrix, seen: set) -> list[str]:
    """The columns of a tidied frame, in the order standardize produces them.

    Slices are not identical: standardize adds a derived column only when it
    carries something, so a county only slice has no SIRUTA column while a
    locality one does. Consolidating slice by slice therefore needs the union,
    and needs it in the order the whole frame would have had, otherwise the CSV
    written without loading everything would differ from the frame returned.
    """
    ordered = [d.label.strip() for d in matrix.dimensions] + [parse.VALUE_COLUMN]
    ordered = [c for c in ordered if c in seen]
    for d in matrix.dimensions:
        col = d.label.strip()
        ordered += [f"{col}{s}" for s in _DERIVED if f"{col}{s}" in seen]
    return ordered + [c for c in seen if c not in ordered]


def _target_folder(folder, code: str) -> tuple[Path, bool]:
    """The working folder, and whether we made it up ourselves."""
    if folder is not None:
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        return path, False
    path = Path(tempfile.gettempdir()) / f"pytempo_{code}"
    path.mkdir(parents=True, exist_ok=True)
    return path, True


def _final_csv(out, folder: Path, temporary: bool, code: str,
               return_df: bool) -> Path | None:
    """Where the consolidated CSV goes, or None when there is nowhere to put it.

    A temporary folder is deleted at the end, so writing the CSV inside it would
    be writing it to nowhere: with no folder and no out, the frame is the whole
    result. Asking for the path instead of the frame then has no answer, and
    saying so beats returning a path to a file that was just removed.
    """
    if out is not None:
        return Path(out)
    if not temporary:
        return folder / f"{code}.csv"
    if not return_df:
        raise ValueError(
            f"{code}: download(return_df=False) returns the path of the CSV, "
            f"so it needs somewhere to leave it. Pass folder='...' or "
            f"out='....csv'.")
    return None


def _fetch(matrix, requests, folder: Path, fmt: str, resume: bool,
           progress: bool) -> tuple[list[Path], list[dict]]:
    """Send the requests, writing each answer to its own file as it arrives.

    A slice that fails after the client has finished retrying is written down
    and skipped: one bad request out of a hundred must not undo the ninety nine
    that worked, and the file it did not write is exactly what makes resume
    ask for it again.
    """
    paths, missing = [], []
    for i, payload in enumerate(requests, 1):
        path = slice_path(folder, i, payload, fmt)
        paths.append(path)
        if resume and path.exists():
            if progress:
                print(f"  {i}/{len(requests)}: {path.name}, already on disk")
            continue
        try:
            df = parse.pivot_csv_to_dataframe(client.post_pivot(payload), matrix)
        except Exception as e:                      # noqa: BLE001
            missing.append({"index": i, "encQuery": payload["encQuery"],
                            "error": f"{type(e).__name__}: {e}"})
            if progress:
                print(f"  {i}/{len(requests)}: FAILED, {type(e).__name__}: {e}")
            continue
        _write_slice(df, path)
        if progress:
            print(f"  {i}/{len(requests)}: +{len(df)} rows -> {path.name}")
    return paths, missing


def _consolidate_frame(paths, matrix, tidy: bool, raw: bool) -> pd.DataFrame:
    """Every slice, read back and concatenated exactly the way get() does."""
    frames = [_read_slice(p, matrix) for p in paths if p.exists()]
    if not frames:
        raise ValueError(
            "nothing was downloaded: every request failed. The messages above "
            "say why; rerun to retry, the work already on disk is kept.")
    df = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
    return _tidied(df, matrix, tidy, raw)


def _consolidate_stream(paths, matrix, destination: Path, tidy: bool,
                        raw: bool) -> int:
    """Slices into one CSV without ever holding more than one of them.

    Two passes over the slices: the first learns which columns the tidied frame
    ends up with, the second writes. Reading a slice twice is cheap; loading a
    matrix that did not fit in memory in the first place is not.
    """
    present = [p for p in paths if p.exists()]
    if not present:
        raise ValueError(
            "nothing was downloaded: every request failed. The messages above "
            "say why; rerun to retry, the work already on disk is kept.")

    seen = set()
    for path in present:
        seen |= set(_tidied(_read_slice(path, matrix), matrix, tidy,
                            raw).columns)
    columns = _ordered_columns(matrix, seen)

    rows = 0
    for n, path in enumerate(present):
        df = _tidied(_read_slice(path, matrix), matrix, tidy, raw)
        df.reindex(columns=columns).to_csv(
            destination, sep=CSV_SEP, index=False, encoding=CSV_ENCODING,
            mode="w" if n == 0 else "a", header=(n == 0))
        rows += len(df)
    return rows


def _clean_up(paths, folder: Path, temporary: bool, destination) -> None:
    """Remove the slices once they are safely inside the CSV, and the temporary
    folder with them. Called only when nothing is missing: while a slice is
    still owed, the ones on disk are the checkpoint resume runs on."""
    for path in paths:
        path.unlink(missing_ok=True)
    if not temporary:
        return
    if destination is not None and destination.resolve().is_relative_to(
            folder.resolve()):
        return              # the CSV asked for lives inside it, so it stays
    shutil.rmtree(folder, ignore_errors=True)


def _report(missing, folder: Path) -> None:
    """What did not come back. Printed even when progress is off: an
    incomplete result that says nothing is worse than a noisy one."""
    print(f"  {len(missing)} slice(s) missing, the rest is complete:")
    for m in missing:
        print(f"    request {m['index']}: {m['error']}")
    print(f"  the slices already fetched are kept in {folder}")
    print("  rerun the same call to ask only for the missing ones")


def run(matrix, requests, folder=None, out=None, return_df: bool = True,
        resume: bool = True, tidy: bool = True, raw: bool = False,
        progress: bool = True):
    """Execute a plan of payloads through disk, and consolidate what came back.

    Returns the tidied DataFrame, or the path of the CSV when return_df is
    False. Missing slices are reported, never raised: they are what the next
    run picks up.
    """
    folder, temporary = _target_folder(folder, matrix.code)
    destination = _final_csv(out, folder, temporary, matrix.code, return_df)
    fmt = slice_format()

    if progress:
        print(f"  slices as {fmt} in {folder}")
    paths, missing = _fetch(matrix, requests, folder, fmt, resume, progress)

    if return_df:
        df = _consolidate_frame(paths, matrix, tidy, raw)
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(destination, sep=CSV_SEP, index=False,
                      encoding=CSV_ENCODING)
        rows = len(df)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = _consolidate_stream(paths, matrix, destination, tidy, raw)
        df = None

    if progress:
        where = f" -> {destination}" if destination is not None else ""
        print(f"  {rows} rows from {len(requests) - len(missing)} "
              f"of {len(requests)} requests{where}")
    if missing:
        _report(missing, folder)
    else:
        _clean_up(paths, folder, temporary, destination)

    if df is None:
        return destination
    # the frame carries what it is missing, so a script can check without
    # reading the printout
    df.attrs["missing_requests"] = missing
    return df
