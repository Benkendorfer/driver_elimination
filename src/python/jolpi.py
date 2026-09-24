import json
from pathlib import Path
import time

import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "jolpi"

# The API allows 4 requests per second and 500 per hour, and returns HTTP 429
# when either is exceeded.
_MIN_INTERVAL = 0.3  # seconds between network requests
_MAX_ATTEMPTS = 5
_last_request = {"time": 0.0}


def _throttled_get(url: str, params: dict) -> requests.Response:
    """GET `url`, spacing out requests and retrying with backoff on HTTP 429.

    Raises:
        requests.HTTPError: On any other HTTP error, or if still throttled
            after `_MAX_ATTEMPTS` attempts.
    """
    attempt = 0
    while True:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request["time"])
        if wait > 0:
            time.sleep(wait)
        _last_request["time"] = time.monotonic()

        resp = requests.get(url, params=params, timeout=10)
        attempt += 1
        throttled = resp.status_code == requests.codes.too_many_requests
        if not throttled or attempt == _MAX_ATTEMPTS:
            resp.raise_for_status()
            return resp
        time.sleep(2 ** (attempt - 1))  # 1, 2, 4, 8 s


def _get(path: str, refresh: bool = False) -> dict:
    """GET `{BASE_URL}/{path}/` and return MRData, caching responses on disk.

    Responses with no races (e.g. a round that hasn't happened yet) are not
    cached, so they are re-fetched next time.
    """
    cache_file = CACHE_DIR / f"{path}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    resp = _throttled_get(f"{BASE_URL}/{path}/", params={"limit": 100})
    data = resp.json()["MRData"]

    if data["RaceTable"]["Races"]:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, indent=2))
    return data


def get_results(year: int, race: int, refresh: bool = False) -> dict | None:
    """Grand Prix results for round `race` of `year`, or None if not run yet.

    Returns the race dict from the API: `raceName`, `date`, `Circuit`, and
    `Results` (one entry per driver, with `position`, `points`, `status`,
    `Driver`, ...). Pass `refresh=True` to bypass the cache, e.g. after a
    post-race penalty.
    """
    races = _get(f"{year}/{race}/results", refresh)["RaceTable"]["Races"]
    return races[0] if races else None
