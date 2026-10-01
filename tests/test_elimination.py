import collections
import itertools
import random

import pytest

import elimination
import season
from season import Session
import standings

RACE = Session(99, "race", "Test GP")
SPRINT = Session(99, "sprint", "Test GP")


def _snapshot(
    points: dict[str, float], wins: dict[str, int] | None = None
) -> standings.Standings:
    wins = wins or {}
    return standings.Standings(
        session=RACE,
        points=points,
        gp_finishes={
            d: collections.Counter({1: wins.get(d, 0)}) for d in points
        },
    )


def _backmarkers(n: int) -> dict[str, float]:
    return {f"back{i}": 0 for i in range(n)}


def _eliminated(
    points: dict[str, float],
    remaining: list[Session],
    wins: dict[str, int] | None = None,
) -> dict[str, bool]:
    snapshot = _snapshot(points, wins)
    return {
        method: elimination.is_eliminated(snapshot, "d", remaining, method)
        for method in elimination.METHODS
    }


@pytest.mark.parametrize(
    ("points", "remaining", "wins", "expected"),
    [
        pytest.param(
            {"d": 0, "a": 10, "b": 10},
            [RACE],
            None,
            {"strict": False, "full_points": True},
            id="someone-must-finish-second",
        ),
        pytest.param(
            {"d": 0, "a": 10, "b": 10} | _backmarkers(10),
            [RACE],
            None,
            {"strict": False, "full_points": False},
            id="backmarkers-absorb-points",
        ),
        pytest.param(
            {"d": 0, "a": 26},
            [RACE],
            None,
            {"strict": True, "full_points": True},
            id="rival-out-of-reach",
        ),
        pytest.param(
            {"d": 0, "a": 25} | _backmarkers(10),
            [RACE],
            None,
            {"strict": False, "full_points": False},
            id="level-on-points-driver-wins-countback",
        ),
        pytest.param(
            {"d": 0, "a": 25} | _backmarkers(10),
            [RACE],
            {"a": 2},
            {"strict": True, "full_points": True},
            id="level-on-points-rival-wins-countback",
        ),
        pytest.param(
            {"d": 0, "a": 3, "b": 3},
            [SPRINT],
            None,
            {"strict": False, "full_points": True},
            id="sprint-only",
        ),
        pytest.param(
            {"d": 30, "a": 20},
            [],
            None,
            {"strict": False, "full_points": False},
            id="season-over-driver-leads",
        ),
        pytest.param(
            {"d": 20, "a": 30},
            [],
            None,
            {"strict": True, "full_points": True},
            id="season-over-driver-behind",
        ),
        pytest.param(
            {"d": 0.5, "a": 25.5} | _backmarkers(10),
            [RACE],
            None,
            {"strict": False, "full_points": False},
            id="half-points-level",
        ),
    ],
)
def test_is_eliminated(
    points: dict[str, float],
    remaining: list[Session],
    wins: dict[str, int] | None,
    expected: dict[str, bool],
) -> None:
    assert _eliminated(points, remaining, wins) == expected


def _can_win_by_brute_force(
    points: dict[str, float], remaining: list[Session]
) -> bool:
    """Try every finishing order with the driver winning every session.

    Assumes no rival has a win yet, so the driver wins any tie on points.
    """
    rivals = [r for r in points if r != "d"]
    best_total = points["d"] + season.max_points(remaining)
    per_session = []
    for session in remaining:
        paying = season.POINTS[session.kind][1:]
        filled = min(len(paying), len(rivals))
        per_session.append(
            [
                dict(zip(order, paying, strict=False))
                for order in itertools.permutations(rivals, filled)
            ]
        )
    for outcome in itertools.product(*per_session):
        totals = dict(points)
        for session_points in outcome:
            for rival, scored in session_points.items():
                totals[rival] += scored
        if all(totals[r] <= best_total for r in rivals):
            return True
    return False


@pytest.mark.parametrize("seed", range(40))
def test_full_points_matches_brute_force(seed: int) -> None:
    rng = random.Random(seed)
    n_rivals = rng.randint(2, 4)
    remaining = [RACE, *rng.sample([RACE, SPRINT], k=rng.randint(0, 1))]
    points: dict[str, float] = {"d": rng.randint(0, 30)}
    for i in range(n_rivals):
        points[f"r{i}"] = rng.randint(0, 50)

    expected = not _can_win_by_brute_force(points, remaining)
    eliminated = elimination.is_eliminated(
        _snapshot(points), "d", remaining, "full_points"
    )
    assert eliminated == expected


@pytest.mark.parametrize("seed", range(40))
def test_full_points_never_less_eliminated_than_strict(seed: int) -> None:
    rng = random.Random(seed)
    points: dict[str, float] = {"d": rng.randint(0, 100)}
    for i in range(rng.randint(1, 12)):
        points[f"r{i}"] = rng.randint(0, 150)
    remaining = [RACE] * rng.randint(0, 3) + [SPRINT] * rng.randint(0, 1)
    result = _eliminated(points, remaining)
    assert result["full_points"] or not result["strict"]


def test_clinch() -> None:
    sprint_2 = Session(2, "sprint", "Two GP")
    race_2 = Session(2, "race", "Two GP")
    results = {
        "ann": elimination.Elimination("ann"),
        "bob": elimination.Elimination(
            "bob", strict=race_2, full_points=race_2
        ),
        "cat": elimination.Elimination(
            "cat", strict=sprint_2, full_points=sprint_2
        ),
    }
    assert elimination.clinch(results, "strict") == ("ann", race_2)

    results["bob"].strict = None
    assert elimination.clinch(results, "strict") is None
