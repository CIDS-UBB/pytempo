"""Strat HTTP subțire peste API-ul TEMPO. Cache pe fișiere, local.

Fără requests_cache global (defectul din tempo.py). Cache-ul e explicit.
get_json: IMPLEMENTAT (iterația 1). post_pivot: iterația 3.
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
    """GET la un endpoint TEMPO, întoarce JSON parsat (dict sau listă).

    Dacă use_cache, salvează răspunsul brut în CACHE_DIR și îl reia de acolo.
    """
    path = _cache_path(url)
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        # INS raspunde 200 cu pagina goala pentru coduri inexistente; nu lasam
        # JSONDecodeError-ul brut din requests sa iasa la suprafata
        raise ValueError(
            f"Raspunsul de la {url} nu e JSON. Cel mai des inseamna ca resursa "
            f"nu exista. Verifica codul cu t.find(...)."
        ) from None

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def url_ok(url: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Verifică rapid că un link răspunde (status 2xx). Pentru testul de linkuri."""
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def post_pivot(payload: dict) -> str:
    """POST la endpoints.pivot(), întoarce textul CSV brut. Iterația 3."""
    raise NotImplementedError("iterația 3")
