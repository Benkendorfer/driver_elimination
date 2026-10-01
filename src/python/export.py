"""Write a season's standings and eliminations as JSON for the website.

    uv run python src/python/export.py 2026

writes `site/data/2026.json`.
"""

import datetime
import json
from pathlib import Path
import sys

import elimination
import jolpi
import season
import standings

DATA_DIR = Path(__file__).resolve().parents[2] / "site" / "data"


def _session_json(
    session: season.Session | None, places: dict[int, str]
) -> dict | None:
    """A session as JSON; `place` is the venue's city, for short labels."""
    if session is None:
        return None
    return {
        "round": session.rnd,
        "kind": session.kind,
        "name": session.name,
        "place": places.get(session.rnd, ""),
    }


def _drivers(year: int) -> dict[str, dict]:
    """Display details per driver ID, with each driver's most recent team."""
    drivers: dict[str, dict] = {}
    sessions = [
        (rnd, race["Results"])
        for rnd, race in jolpi.get_year_race_results(year).items()
        if race is not None
    ] + [
        (rnd, sprint["SprintResults"])
        for rnd, sprint in jolpi.get_year_sprint_results(year).items()
        if sprint is not None
    ]
    for _, results in sorted(sessions, key=lambda item: item[0]):
        for result in results:
            driver = result["Driver"]
            drivers[driver["driverId"]] = {
                "code": driver.get("code", ""),
                "name": f"{driver['givenName']} {driver['familyName']}",
                "given_name": driver["givenName"],
                "family_name": driver["familyName"],
                # The API calls some teams "Haas F1 Team" etc. but not others.
                "team": result["Constructor"]["name"].removesuffix(" F1 Team"),
            }
    return drivers


def build(year: int) -> dict:
    """The JSON document for `year`, as a dict."""
    snapshots = standings.standings_by_session(year)
    all_sessions = season.sessions(year)
    if not snapshots:
        latest = None
        remaining = all_sessions
    else:
        latest = snapshots[-1]
        remaining = season.remaining_after(all_sessions, latest.session)
    results = elimination.eliminations(year)
    details = _drivers(year)
    places = {
        int(race["round"]): race["Circuit"]["Location"]["locality"]
        for race in jolpi.get_year_races(year)
    }

    drivers = []
    if latest is not None:
        for position, driver in enumerate(latest.ranking(), start=1):
            elim = results[driver]
            drivers.append(
                {
                    "id": driver,
                    **details[driver],
                    "position": position,
                    "points": latest.points[driver],
                    "wins": latest.gp_finishes[driver][1],
                    "eliminated": {
                        method: _session_json(getattr(elim, method), places)
                        for method in elimination.METHODS
                    },
                }
            )

    clinches = {}
    for method in elimination.METHODS:
        decided = elimination.clinch(results, method)
        clinches[method] = decided and {
            "driver": decided[0],
            "session": _session_json(decided[1], places),
        }

    return {
        "season": year,
        "updated": datetime.datetime.now(datetime.UTC).isoformat(
            timespec="seconds"
        ),
        "last_session": _session_json(
            latest.session if latest else None, places
        ),
        "remaining": {
            "races": sum(s.kind == "race" for s in remaining),
            "sprints": sum(s.kind == "sprint" for s in remaining),
            "max_points": season.max_points(remaining),
        },
        "clinch": clinches,
        "drivers": drivers,
    }


def main() -> None:
    """Write `site/data/<year>.json`."""
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{year}.json"
    path.write_text(json.dumps(build(year), indent=2) + "\n")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
