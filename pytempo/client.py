"""A thin HTTP layer over the TEMPO API, with a local file cache.

No global requests_cache: the cache is explicit, so you can always tell whether
a call touched the network.

The POST to pivot retries. Measured on the real server: heavy requests come back
with 'Read timed out' often enough that a single miss used to sink a whole
download of a hundred requests. Metadata GETs are small and quick, so they stay
as they were.
"""
import hashlib
import json
import os
import pathlib
import time

import requests

from . import endpoints

CACHE_DIR = pathlib.Path(os.environ.get("TEMPO_CACHE_DIR", "data/raw"))
DEFAULT_TIMEOUT = 30

# a heavy pivot request on a slow day needs more than the 30s the GETs use
PIVOT_TIMEOUT = 60
# how many times a pivot request is sent before giving up, and how long to wait
# between attempts. The waits grow: a server under load needs time, not a
# faster knock. The third wait is there for anyone raising PIVOT_ATTEMPTS
PIVOT_ATTEMPTS = 3
PIVOT_BACKOFF = (5, 15, 45)


class ServerUnavailable(RuntimeError):
    """The INS server did not answer, after every retry. Not a data error."""


def _cache_path(url: str) -> pathlib.Path:
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{key}.json"


def get_json(url: str, use_cache: bool = True, timeout: int = DEFAULT_TIMEOUT):
    """GET a TEMPO endpoint and return parsed JSON, a dict or a list.

    With use_cache, the raw response is stored under CACHE_DIR and read back
    from there next time.
    """
    path = _cache_path(url)
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        # INS answers 200 with an empty page for codes that do not exist; do
        # not let the raw JSONDecodeError from requests reach the caller
        raise ValueError(
            f"The response from {url} is not JSON. Most often that means the "
            f"resource does not exist. Check the code with t.find(...)."
        ) from None

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def url_ok(url: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Quick check that a link answers with status 200."""
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _wait_before(attempt: int) -> int:
    """How long to wait before attempt number `attempt`, counting from 2."""
    return PIVOT_BACKOFF[min(attempt - 2, len(PIVOT_BACKOFF) - 1)]


def post_pivot(payload: dict, timeout: int | None = None,
               attempts: int = PIVOT_ATTEMPTS) -> str:
    """POST to endpoints.pivot() and return the raw CSV text. No parsing here.

    A timeout, a dropped connection or a 5xx is the server having a bad moment,
    so the request is sent again after a growing wait. A 4xx is our own bad
    request and surfaces at once: retrying it would only be slower.
    """
    if timeout is None:
        timeout = PIVOT_TIMEOUT

    last = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            time.sleep(_wait_before(attempt))
        try:
            resp = requests.post(
                endpoints.pivot(),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
            continue
        if resp.status_code < 500:
            resp.raise_for_status()
            return resp.text
        last = requests.HTTPError(
            f"HTTP {resp.status_code} from pivot", response=resp)

    raise ServerUnavailable(
        f"The INS server did not answer after {attempts} attempts "
        f"({type(last).__name__}: {last}). It is the server, not the query. "
        f"Try again later; with download(resume=True) the work already on disk "
        f"is kept and only the missing pieces are asked for again."
    ) from last
