"""Module for querying the jolpica-F1 API."""

import datetime
import json
import logging
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


logger = logging.getLogger(__name__)


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

        logger.info("GET %s attempt %i", url, attempt)
        resp = requests.get(url, params=params, timeout=10)
        attempt += 1
        throttled = resp.status_code == requests.codes.too_many_requests
        if not throttled or attempt == _MAX_ATTEMPTS:
            resp.raise_for_status()
            return resp
        time.sleep(2 ** (attempt - 1))  # 1, 2, 4, 8 s


def _get(path: str, *, refresh: bool = False) -> dict:
    """GET `{BASE_URL}/{path}/` and return MRData, caching responses on disk.

    Responses with no races (e.g. a round that hasn't happened yet) are not
    cached, so they are re-fetched next time.
    """
    cache_file = CACHE_DIR / f"{path}.json"
    if cache_file.exists() and not refresh:
        logger.debug("Cache hit: %s", cache_file)
        return json.loads(cache_file.read_text())

    resp = _throttled_get(f"{BASE_URL}/{path}/", params={"limit": 100})
    data = resp.json()["MRData"]

    if data["RaceTable"]["Races"]:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file and rename, so an interrupted write can't leave a
        # half-written cache file behind.
        tmp_file = cache_file.with_suffix(".json.tmp")
        tmp_file.write_text(json.dumps(data, indent=2))
        tmp_file.replace(cache_file)
    return data


def get_results(year: int, race: int, *, refresh: bool = False) -> dict | None:
    """Grand Prix results for round `race` of `year`, or None if not run yet.

    Returns the race dict from the API: `raceName`, `date`, `Circuit`, and
    `Results` (one entry per driver, with `position`, `points`, `status`,
    `Driver`, ...). Pass `refresh=True` to bypass the cache, e.g. after a
    post-race penalty.
    """
    data = _get(f"{year}/{race}/results", refresh=refresh)
    races = data["RaceTable"]["Races"]
    return races[0] if races else None


def get_year_races(year: int, *, refresh: bool = False) -> list[dict]:
    """The calendar for `year`: one dict per round, in round order.

    Each dict has `round`, `raceName`, `date`, `time`, `Circuit`, and the
    session times; sprint weekends also have a `Sprint` entry.
    """
    return _get(f"{year}/races", refresh=refresh)["RaceTable"]["Races"]


def _race_start(race: dict) -> datetime.datetime:
    """Start of the Grand Prix in UTC, from a calendar entry.

    Falls back to midnight UTC on the race date if the API gives no time.
    """
    time_str = race.get("time", "00:00:00Z").replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(f"{race['date']}T{time_str}")


def get_year_results(
    year: int,
    from_race: int = 1,
    *,
    refresh: bool = False,
    include_future: bool = False,
) -> dict[int, dict | None]:
    """Grand Prix results for `year`, from round `from_race` onwards.

    Args:
        year: Season to fetch.
        from_race: First round to include.
        refresh: Re-download the calendar. Results for individual rounds stay
            cached; use `get_results(..., refresh=True)` to re-download one.
        include_future: Also include rounds that haven't started yet, with
            value None. Otherwise they are left out.

    Returns:
        A dict mapping round number to that round's race dict (as returned by
        `get_results`), e.g. {1: {...}, 2: {...}}. The value is None for a
        round that has started but whose results aren't published yet, and
        for future rounds if `include_future` is set.
    """
    now = datetime.datetime.now(datetime.UTC)

    results: dict[int, dict | None] = {}
    for race in get_year_races(year, refresh=refresh):
        rnd = int(race["round"])
        if rnd < from_race:
            continue
        if _race_start(race) > now:
            if not include_future:
                break  # the calendar is in date order, so the rest are future
            results[rnd] = None
            continue
        results[rnd] = get_results(year, rnd)

    return results
