import json
from pathlib import Path

import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "jolpi"


def _get(path: str, refresh: bool = False) -> dict:
    """GET `{BASE_URL}/{path}/` and return MRData, caching responses on disk.

    Responses with no races (e.g. a round that hasn't happened yet) are not
    cached, so they are re-fetched next time.
    """
    cache_file = CACHE_DIR / f"{path}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    resp = requests.get(
        f"{BASE_URL}/{path}/", params={"limit": 100}, timeout=10
    )
    resp.raise_for_status()
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
