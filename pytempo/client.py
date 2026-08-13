"""A thin HTTP layer over the TEMPO API, with a local file cache.

No global requests_cache: the cache is explicit, so you can always tell whether
a call touched the network.
"""
import hashlib
import json
import os
import pathlib

import requests

from . import endpoints

CACHE_DIR = pathlib.Path(os.environ.get("TEMPO_CACHE_DIR", "data/raw"))
DEFAULT_TIMEOUT = 30


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


def post_pivot(payload: dict, timeout: int = DEFAULT_TIMEOUT) -> str:
    """POST to endpoints.pivot() and return the raw CSV text. No parsing here."""
    resp = requests.post(
        endpoints.pivot(),
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text
