"""Drivers' championship standings after each points-scoring session.

A season is a sequence of sessions in date order: on a sprint weekend the
sprint comes before that round's Grand Prix. `standings_by_session` returns
the cumulative standings after each one, which is where elimination gets
checked.

Run as a script to print the latest standings and compare every round against
the official standings from the API:

    uv run python src/python/standings.py 2026
"""

import collections
import dataclasses
import itertools
import logging
import sys
from typing import Literal

import jolpi

logger = logging.getLogger(__name__)

SessionKind = Literal["sprint", "race"]

# Finishing positions considered for the countback tie-break. Larger than any
# grid, so a tie is only left unresolved if two drivers' results are identical.
_MAX_POSITION = 30


@dataclasses.dataclass(frozen=True)
class Session:
    """A points-scoring session: a round's sprint or its Grand Prix."""

    rnd: int
    kind: SessionKind
    name: str  # e.g. "Chinese Grand Prix"


@dataclasses.dataclass
class Standings:
    """Cumulative championship standings after `session`.

    Attributes:
        session: The session these standings are after.
        points: Points per driver, keyed by API `driverId` (e.g. "russell").
        gp_finishes: Classified Grand Prix finishing positions per driver, as
            {position: count}, for the countback tie-break. Sprints don't
            count towards countback.
    """

    session: Session
    points: dict[str, float]
    gp_finishes: dict[str, collections.Counter[int]]

    def rank_key(self, driver: str) -> tuple:
        """Sort key for championship order; lower is better.

        Points first, then countback: most wins, then most 2nd places, and so
        on. Drivers with equal keys are genuinely tied.
        """
        finishes = self.gp_finishes[driver]
        countback = tuple(-finishes[p] for p in range(1, _MAX_POSITION + 1))
        return (-self.points[driver], countback)

    def ranking(self) -> list[str]:
        """Driver IDs in championship order, with exact ties ordered by ID."""
        return sorted(self.points, key=lambda d: (self.rank_key(d), d))


def _add_results(
    results: list[dict],
    points: dict[str, float],
    gp_finishes: dict[str, collections.Counter[int]] | None,
) -> None:
    """Add one session's results to the running totals, in place.

    Pass `gp_finishes` only for a Grand Prix, so sprints don't count towards
    countback.
    """
    for result in results:
        driver = result["Driver"]["driverId"]
        points[driver] = points.get(driver, 0.0) + float(result["points"])
        if gp_finishes is not None:
            finishes = gp_finishes.setdefault(driver, collections.Counter())
            # positionText is a number for classified finishers, and a letter
            # otherwise (R = retired, D = disqualified, W = withdrawn, ...).
            if result["positionText"].isdigit():
                finishes[int(result["positionText"])] += 1


def standings_by_session(year: int) -> list[Standings]:
    """Standings after every sprint and Grand Prix of `year` run so far.

    Uses the points the API awards for each result, so penalties,
    disqualifications and reduced points are already accounted for.

    Returns:
        One `Standings` per session, in date order.
    """
    races = jolpi.get_year_race_results(year)
    sprints = jolpi.get_year_sprint_results(year)

    points: dict[str, float] = {}
    gp_finishes: dict[str, collections.Counter[int]] = {}
    standings = []

    def snapshot(session: Session) -> Standings:
        return Standings(
            session=session,
            points=dict(points),
            gp_finishes={
                driver: collections.Counter(gp_finishes.get(driver, {}))
                for driver in points
            },
        )

    for rnd in sorted(races.keys() | sprints.keys()):
        sprint = sprints.get(rnd)
        if sprint is not None:
            _add_results(sprint["SprintResults"], points, gp_finishes=None)
            standings.append(
                snapshot(Session(rnd, "sprint", sprint["raceName"]))
            )

        race = races.get(rnd)
        if race is not None:
            _add_results(race["Results"], points, gp_finishes)
            standings.append(snapshot(Session(rnd, "race", race["raceName"])))

    return standings


def check_against_api(year: int, standings: list[Standings]) -> list[str]:
    """Compare computed standings with the official ones after each round.

    The API publishes standings once per round (after the Grand Prix), so only
    those sessions are checked.

    Returns:
        A description of each mismatch in points or order; empty if all match.
    """
    problems = []
    for computed in standings:
        session = computed.session
        if session.kind != "race":
            continue
        official = jolpi.get_driver_standings(year, session.rnd)
        if official is None:
            problems.append(f"Round {session.rnd}: no official standings")
            continue

        official_points = {
            entry["Driver"]["driverId"]: float(entry["points"])
            for entry in official
        }
        if official_points != computed.points:
            drivers = official_points.keys() | computed.points.keys()
            diffs = {
                driver: (
                    computed.points.get(driver),
                    official_points.get(driver),
                )
                for driver in sorted(drivers)
                if computed.points.get(driver) != official_points.get(driver)
            }
            problems.append(
                f"Round {session.rnd}: points (computed, official) {diffs}"
            )

        # The API lists exactly tied drivers (e.g. several on 0 points with no
        # classified finish) in an arbitrary order, so only check that each
        # driver isn't ranked above someone our tie-break puts ahead of them.
        official_order = [entry["Driver"]["driverId"] for entry in official]
        for ahead, behind in itertools.pairwise(official_order):
            if computed.rank_key(ahead) > computed.rank_key(behind):
                problems.append(
                    f"Round {session.rnd}: official order has {ahead} ahead "
                    f"of {behind}"
                )
    return problems


def main() -> None:
    """Print the latest standings and check all rounds against the API."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026

    standings = standings_by_session(year)
    if not standings:
        print(f"No results for {year} yet")
        return

    latest = standings[-1]
    print(
        f"Standings after round {latest.session.rnd} "
        f"({latest.session.name}, {latest.session.kind}):"
    )
    for position, driver in enumerate(latest.ranking(), start=1):
        wins = latest.gp_finishes[driver][1]
        print(
            f"{position:3}  {driver:20} {latest.points[driver]:6g} pts"
            f"  {wins} wins"
        )

    problems = check_against_api(year, standings)
    print()
    if problems:
        print("Mismatches with the official standings:")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("All rounds match the official standings.")


if __name__ == "__main__":
    main()
