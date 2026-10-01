import pytest

import jolpi
import standings


def _result(driver: str, position: str, points: float) -> dict:
    return {
        "Driver": {"driverId": driver},
        "positionText": position,
        "points": str(points),
    }


@pytest.fixture
def season_data(monkeypatch: pytest.MonkeyPatch) -> None:
    races = {
        1: {
            "raceName": "One GP",
            "Results": [
                _result("ann", "1", 25),
                _result("bob", "2", 18),
                _result("cat", "R", 0),
            ],
        },
        2: {
            "raceName": "Two GP",
            "Results": [
                _result("bob", "1", 25),
                _result("ann", "2", 18),
                _result("cat", "3", 15),
            ],
        },
    }
    sprints = {
        2: {
            "raceName": "Two GP",
            "SprintResults": [
                _result("cat", "1", 8),
                _result("ann", "2", 7),
                _result("bob", "3", 6),
            ],
        },
    }
    monkeypatch.setattr(jolpi, "get_year_race_results", lambda _year: races)
    monkeypatch.setattr(jolpi, "get_year_sprint_results", lambda _year: sprints)


@pytest.mark.usefixtures("season_data")
def test_one_snapshot_per_session_in_order() -> None:
    sessions = [s.session for s in standings.standings_by_session(2026)]
    assert [(s.rnd, s.kind) for s in sessions] == [
        (1, "race"),
        (2, "sprint"),
        (2, "race"),
    ]


@pytest.mark.usefixtures("season_data")
def test_points_accumulate() -> None:
    after_r1, after_sprint, after_r2 = standings.standings_by_session(2026)
    assert after_r1.points == {"ann": 25, "bob": 18, "cat": 0}
    assert after_sprint.points == {"ann": 32, "bob": 24, "cat": 8}
    assert after_r2.points == {"ann": 50, "bob": 49, "cat": 23}


@pytest.mark.usefixtures("season_data")
def test_snapshots_are_independent() -> None:
    after_r1, _, _ = standings.standings_by_session(2026)
    assert after_r1.gp_finishes["bob"][1] == 0


@pytest.mark.usefixtures("season_data")
def test_countback_ignores_sprints_and_unclassified() -> None:
    final = standings.standings_by_session(2026)[-1]
    assert final.gp_finishes["cat"] == {3: 1}  # sprint win and DNF ignored
    assert final.gp_finishes["ann"] == {1: 1, 2: 1}


def test_ranking_breaks_ties_on_countback() -> None:
    snapshot = standings.Standings(
        session=None,  # type: ignore[arg-type]
        points={"ann": 43, "bob": 43, "cat": 50},
        gp_finishes={
            "ann": standings.collections.Counter({2: 2, 7: 1}),
            "bob": standings.collections.Counter({1: 1, 2: 1}),
            "cat": standings.collections.Counter({1: 2}),
        },
    )
    assert snapshot.ranking() == ["cat", "bob", "ann"]
