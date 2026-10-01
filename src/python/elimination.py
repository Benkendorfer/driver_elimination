"""When each driver is eliminated from the drivers' championship.

A driver d is still in contention if some way of finishing the season makes
them champion. Their best case is always to win every remaining session, so
the question is whether the other drivers' points can stay below d's.

Two definitions are computed:

- "strict": any outcome is possible, including every other car retiring from
  every remaining race. The other drivers can then score nothing more, so d is
  eliminated only once someone is already out of reach on points.
- "full points": every points-paying position in every remaining session is
  awarded to someone. Someone has to finish 2nd, 3rd, ... behind d, so d can
  be eliminated earlier. Decided with an integer linear program.

Run as a script to print every driver's elimination points:

    uv run python src/python/elimination.py 2026
"""

import collections
import dataclasses
import math
import sys
from typing import Literal

import pulp

import season
import standings

Method = Literal["strict", "full_points"]
METHODS: tuple[Method, ...] = ("strict", "full_points")


def _countback(finishes: collections.Counter[int]) -> tuple[int, ...]:
    """(wins, 2nd places, 3rd places, ...): higher wins a tie on points."""
    return tuple(finishes[p] for p in range(1, standings.MAX_POSITION + 1))


def _allowance(gap: float, *, driver_wins_tie: bool) -> int:
    """Most points a rival `gap` points behind d's best total can still score.

    Points scored from here on are whole numbers. A rival may draw level with
    d only if d wins the tie-break.
    """
    if driver_wins_tie:
        return math.floor(gap)
    return math.ceil(gap) - 1


def is_eliminated(
    snapshot: standings.Standings,
    driver: str,
    remaining: list[season.Session],
    method: Method,
) -> bool:
    """Whether `driver` can no longer become champion, under `method`.

    Args:
        snapshot: Standings now.
        driver: The driver to check, by API `driverId`.
        remaining: The sessions still to come, in any order.
        method: Which definition of elimination to use; see the module
            docstring.
    """
    # Best case for `driver`: win every remaining session.
    best_total = snapshot.points[driver] + season.max_points(remaining)
    gps_left = sum(s.kind == "race" for s in remaining)
    best_finishes = collections.Counter(snapshot.gp_finishes[driver])
    best_finishes[1] += gps_left
    best_countback = _countback(best_finishes)

    allowances = {}
    for rival, points in snapshot.points.items():
        if rival == driver:
            continue
        # Rivals can't win a remaining Grand Prix, so their win count is final.
        # Exact for "strict", where rivals score nothing more. For "full
        # points", rivals can still add 2nd places; on equal wins we let the
        # driver win the tie, so a driver is never wrongly eliminated.
        rival_countback = _countback(snapshot.gp_finishes[rival])
        if method == "strict":
            driver_wins_tie = best_countback >= rival_countback
        else:
            driver_wins_tie = best_countback[0] >= rival_countback[0]
        allowances[rival] = _allowance(
            best_total - points, driver_wins_tie=driver_wins_tie
        )

    # Someone is already out of reach, whatever happens.
    if any(allowance < 0 for allowance in allowances.values()):
        return True
    if method == "strict" or not remaining:
        return False

    # Nobody can get past the driver even finishing 2nd in every session.
    most_for_a_rival = sum(season.POINTS[s.kind][1] for s in remaining)
    if all(allowance >= most_for_a_rival for allowance in allowances.values()):
        return False

    return not _full_points_feasible(allowances, remaining)


def _full_points_feasible(
    allowances: dict[str, int], remaining: list[season.Session]
) -> bool:
    """Whether the points behind a winner of every session can be shared out.

    Every points-paying position from 2nd down in every session in `remaining`
    must go to a different rival in that session, without any rival scoring
    more than their allowance.
    """
    # Rivals who can't exceed their allowance even finishing 2nd every time
    # need no limit, and are interchangeable: they are modelled as one pool
    # that can take up to that many positions per session. This keeps the
    # model small, as usually only a few rivals are close enough to matter.
    most_for_a_rival = sum(season.POINTS[s.kind][1] for s in remaining)
    capped = [r for r, a in allowances.items() if a < most_for_a_rival]
    pool_size = len(allowances) - len(capped)

    problem = pulp.LpProblem("elimination", pulp.LpMinimize)
    scored = {r: [] for r in capped}  # each capped rival's points, to sum
    for s, session in enumerate(remaining):
        points = season.POINTS[session.kind]
        # Positions are 2nd and below (1st is the driver), and only those
        # paying points: a rival outside them scores nothing. With fewer
        # rivals than paying positions, the lowest ones stay empty.
        positions = range(2, min(len(points), len(allowances) + 1) + 1)

        # x[r, p] = 1 if capped rival r finishes in position p of session s;
        # pool[p] = 1 if a rival from the pool does.
        x = {
            (r, p): problem.add_variable(f"x_{r}_{s}_{p}", cat="Binary")
            for r in capped
            for p in positions
        }
        pool = {
            p: problem.add_variable(f"pool_{s}_{p}", cat="Binary")
            for p in positions
        }

        # Every paying position is filled by exactly one rival...
        for p in positions:
            problem += pulp.lpSum(x[r, p] for r in capped) + pool[p] == 1
        # ...and each rival finishes in at most one position.
        for r in capped:
            problem += pulp.lpSum(x[r, p] for p in positions) <= 1
            scored[r] += [points[p - 1] * x[r, p] for p in positions]
        problem += pulp.lpSum(pool.values()) <= pool_size

    # Nobody scores more than they can afford.
    for r in capped:
        problem += pulp.lpSum(scored[r]) <= allowances[r]

    problem.solve(pulp.HiGHS(msg=False))
    status = pulp.LpStatus[problem.status]
    if status not in {"Optimal", "Infeasible"}:
        msg = f"Unexpected solver status: {status}"
        raise RuntimeError(msg)
    return status == "Optimal"


@dataclasses.dataclass
class Elimination:
    """When a driver was eliminated under each method; None if still in it."""

    driver: str
    strict: season.Session | None = None
    full_points: season.Session | None = None


def eliminations(year: int) -> dict[str, Elimination]:
    """Each driver's elimination point under both methods, for `year` so far.

    Drivers are keyed by API `driverId`. Once eliminated, a driver stays
    eliminated, so each driver is only checked until both are found.
    """
    sessions = season.sessions(year)
    result: dict[str, Elimination] = {}
    for snapshot in standings.standings_by_session(year):
        remaining = season.remaining_after(sessions, snapshot.session)
        for driver in snapshot.points:
            elim = result.setdefault(driver, Elimination(driver))
            for method in METHODS:
                if getattr(elim, method) is None and is_eliminated(
                    snapshot, driver, remaining, method
                ):
                    setattr(elim, method, snapshot.session)
    return result


def clinch(
    results: dict[str, Elimination], method: Method
) -> tuple[str, season.Session] | None:
    """The champion and the session they clinched the title, if decided.

    The title is clinched once every other driver is eliminated.
    """
    alive = [e.driver for e in results.values() if getattr(e, method) is None]
    if len(alive) != 1:
        return None
    others = [
        getattr(e, method) for e in results.values() if e.driver != alive[0]
    ]
    # Within a round the sprint comes before the race.
    last = max(others, key=lambda s: (s.rnd, s.kind == "race"))
    return alive[0], last


def _describe(session: season.Session | None) -> str:
    if session is None:
        return "-"
    return f"R{session.rnd} {session.name} ({session.kind})"


def main() -> None:
    """Print each driver's elimination points for a season."""
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    results = eliminations(year)
    latest = standings.standings_by_session(year)[-1]

    print(f"{'Driver':20} {'Pts':>5}  {'Out (full points)':38} Out (strict)")
    for driver in latest.ranking():
        elim = results[driver]
        print(
            f"{driver:20} {latest.points[driver]:5g}  "
            f"{_describe(elim.full_points):38} {_describe(elim.strict)}"
        )

    print()
    for method in METHODS:
        decided = clinch(results, method)
        if decided:
            champion, session = decided
            print(f"{method}: {champion} clinched at {_describe(session)}")
        else:
            print(f"{method}: title not decided yet")


if __name__ == "__main__":
    main()
