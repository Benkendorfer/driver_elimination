import pytest

import jolpi
import season
from season import Session


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    races = [
        {"round": "1", "raceName": "One GP"},
        {"round": "2", "raceName": "Two GP", "Sprint": {"date": "2026-01-01"}},
        {"round": "3", "raceName": "Three GP"},
    ]
    monkeypatch.setattr(jolpi, "get_year_races", lambda _year: races)


@pytest.mark.usefixtures("calendar")
def test_sessions_put_sprint_before_its_race() -> None:
    assert season.sessions(2026) == [
        Session(1, "race", "One GP"),
        Session(2, "sprint", "Two GP"),
        Session(2, "race", "Two GP"),
        Session(3, "race", "Three GP"),
    ]


@pytest.mark.usefixtures("calendar")
def test_remaining_after() -> None:
    all_sessions = season.sessions(2026)
    remaining = season.remaining_after(all_sessions, all_sessions[1])
    assert [(s.rnd, s.kind) for s in remaining] == [(2, "race"), (3, "race")]
    assert season.remaining_after(all_sessions, all_sessions[-1]) == []


@pytest.mark.usefixtures("calendar")
def test_remaining_after_unknown_session_raises() -> None:
    with pytest.raises(ValueError, match="No sprint in round 1"):
        season.remaining_after(
            season.sessions(2026), Session(1, "sprint", "One GP")
        )


def test_max_points() -> None:
    remaining = [
        Session(1, "race", ""),
        Session(2, "sprint", ""),
        Session(2, "race", ""),
    ]
    assert season.max_points(remaining) == 25 + 8 + 25
    assert season.max_points([]) == 0
