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
import time
from pathlib import Path

import pandas as pd

from . import client, parse, selection

# seconds to wait between one request and the next. Measured on POP108D, 83
# slices: fired back to back, the first 42 answered with data and every one of
# the remaining 41 came back empty, which is INS rate limiting. Half a second
# between them costs under a minute on a download of a hundred and keeps the
# server willing. Set pytempo.incremental.REQUEST_SPACING = 0 to turn it off
REQUEST_SPACING = 0.5

# when slices start failing anyway, the spacing doubles, up to this. INS has
# had enough, and knocking harder is not an argument
MAX_SPACING = 8.0

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

    Requests are spaced out, and the spacing grows every time a slice fails
    anyway. A download of a hundred requests is a guest asking for a lot, and
    the way INS says so is by answering with nothing.
    """
    paths, missing = [], []
    spacing = REQUEST_SPACING
    sent = False
    for i, payload in enumerate(requests, 1):
        path = slice_path(folder, i, payload, fmt)
        paths.append(path)
        if resume and path.exists():
            if progress:
                print(f"  {i}/{len(requests)}: {path.name}, already on disk")
            continue
        if sent and spacing:
            time.sleep(spacing)
        sent = True
        try:
            df = parse.pivot_csv_to_dataframe(client.post_pivot(payload), matrix)
        except Exception as e:                      # noqa: BLE001
            missing.append({"index": i, "encQuery": payload["encQuery"],
                            "error": f"{type(e).__name__}: {e}"})
            spacing = min(max(spacing * 2, 1.0), MAX_SPACING)
            if progress:
                print(f"  {i}/{len(requests)}: FAILED, {type(e).__name__}: {e}")
                print(f"       slowing down, {spacing}s between requests from "
                      f"here")
            continue
        _write_slice(df, path)
        if progress:
            print(f"  {i}/{len(requests)}: +{len(df)} rows -> {path.name}")
    return paths, missing


def _consolidate_frame(paths, matrix, tidy: bool, raw: bool):
    """Every slice, read back and concatenated exactly the way get() does.

    Returns the frame and the row count of each slice, which is what the
    aggregation check compares the joined frame against.
    """
    frames = [_read_slice(p, matrix) for p in paths if p.exists()]
    if not frames:
        raise ValueError(
            "nothing was downloaded: every request failed. The messages above "
            "say why; rerun to retry, the work already on disk is kept.")
    df = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
    return _tidied(df, matrix, tidy, raw), [len(f) for f in frames]


def _consolidate_stream(paths, matrix, destination: Path, tidy: bool,
                        raw: bool):
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

    counts = []
    for n, path in enumerate(present):
        df = _tidied(_read_slice(path, matrix), matrix, tidy, raw)
        df.reindex(columns=columns).to_csv(
            destination, sep=CSV_SEP, index=False, encoding=CSV_ENCODING,
            mode="w" if n == 0 else "a", header=(n == 0))
        counts.append(len(df))
    return sum(counts), counts


def _verify_aggregation(df, matrix, planned: int, slice_rows: list[int],
                        missing=None, select: dict | None = None) -> list[str]:
    """What can go wrong between many slices and one frame, checked out loud.

    A download of a hundred requests fails quietly in ways a single request
    cannot: a slice that never arrived, a piece counted twice, a filter that
    did not reach the query. None of that shows up as an exception, only as a
    file that looks finished and is not. So the joining is checked and anything
    odd is said, in the plainest terms available.

    Returns one line per problem, empty when everything holds. df is None on
    the streaming path, where the frame is never assembled: the two checks that
    need it say so rather than passing by default.
    """
    problems = []
    missing = list(missing or [])
    written = len(slice_rows)

    if written != planned:
        absent = ", ".join(str(m["index"]) for m in missing) or "unknown"
        problems.append(
            f"INCOMPLETE: {written} of {planned} slices are on disk, so this "
            f"is not the whole indicator. Requests missing: {absent}")

    expected_rows = sum(slice_rows)
    if df is None:
        problems.append(
            "not checked: duplicate keys and the select filter need the frame, "
            "which return_df=False never assembles")
    else:
        if len(df) != expected_rows:
            problems.append(
                f"ROWS: the joined frame has {len(df)} rows, the slices held "
                f"{expected_rows}. Something was lost or doubled on the join")

        key = [d.label.strip() for d in matrix.dimensions
               if d.label.strip() in df.columns]
        duplicated = int(df.duplicated(key).sum()) if key else 0
        if duplicated:
            problems.append(
                f"DUPLICATES: {duplicated} rows repeat a combination of "
                f"{len(key)} dimension columns that can only occur once")

        problems += _verify_select(df, matrix, select)
    return problems


def _verify_select(df, matrix, select: dict | None) -> list[str]:
    """Did the filter reach the query, and did it cut exactly what was named.

    Too many distinct values means select never made it into the request; too
    few means it cut deeper than asked, or that INS simply has no data for the
    rest, which is common enough to be said out loud rather than assumed.
    """
    if not select:
        return []

    problems = []
    for key in select:
        dimension = selection.find_dimension(matrix.dimensions, key)
        column = dimension.label.strip()
        if column not in df.columns:
            continue
        wanted = len(dimension.options)
        found = int(df[column].nunique())
        if found > wanted:
            problems.append(
                f"SELECT: {column} came back with {found} distinct values, "
                f"{wanted} were selected. The filter did not reach the query")
        elif found < wanted:
            problems.append(
                f"SELECT: {column} came back with {found} distinct values of "
                f"the {wanted} selected. Either the filter cut too deep, or "
                f"INS has no data for the rest")
    return problems


def _announce(problems: list[str], rows: int, progress: bool) -> None:
    """The verdict of the checks. Problems are printed whatever progress says:
    a frame that is quietly wrong is worse than a noisy one."""
    if not problems:
        if progress:
            print(f"  aggregation check: {rows} rows, complete, no duplicates")
        return
    print("  aggregation check:")
    for line in problems:
        print(f"    {line}")


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
        progress: bool = True, select: dict | None = None):
    """Execute a plan of payloads through disk, and consolidate what came back.

    Returns the tidied DataFrame, or the path of the CSV when return_df is
    False. Missing slices are reported, never raised: they are what the next
    run picks up. select is not used to fetch anything, the payloads already
    carry it; it is passed so the aggregation check can confirm the filter
    survived the round trip.
    """
    folder, temporary = _target_folder(folder, matrix.code)
    destination = _final_csv(out, folder, temporary, matrix.code, return_df)
    fmt = slice_format()

    if progress:
        print(f"  slices as {fmt} in {folder}")
    paths, missing = _fetch(matrix, requests, folder, fmt, resume, progress)

    if return_df:
        df, slice_rows = _consolidate_frame(paths, matrix, tidy, raw)
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(destination, sep=CSV_SEP, index=False,
                      encoding=CSV_ENCODING)
        rows = len(df)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows, slice_rows = _consolidate_stream(paths, matrix, destination,
                                               tidy, raw)
        df = None

    if progress:
        where = f" -> {destination}" if destination is not None else ""
        print(f"  {rows} rows from {len(requests) - len(missing)} "
              f"of {len(requests)} requests{where}")
    if missing:
        _report(missing, folder)
    else:
        _clean_up(paths, folder, temporary, destination)

    problems = _verify_aggregation(df, matrix, len(requests), slice_rows,
                                   missing, select)
    _announce(problems, rows, progress)

    if df is None:
        return destination
    # the frame carries the verdict too, so a script can check without reading
    # the printout
    df.attrs["missing_requests"] = missing
    df.attrs["complete"] = not missing
    df.attrs["aggregation_warnings"] = problems
    return df
