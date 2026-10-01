"""The points-scoring sessions of a season, and what is left after each one.

A season is a sequence of sessions in date order: every round has a Grand
Prix, and sprint weekends also have a sprint the day before.

Run as a script to print, after each session run so far, how many races are
left and how many points one driver can still score:

    uv run python src/python/season.py 2026
"""

import dataclasses
import sys
from typing import Literal

import jolpi

SessionKind = Literal["sprint", "race"]

# Points for 1st, 2nd, ... in each kind of session. This is the system used
# from 2025 onwards (no fastest-lap point); earlier seasons differ.
POINTS: dict[SessionKind, tuple[int, ...]] = {
    "race": (25, 18, 15, 12, 10, 8, 6, 4, 2, 1),
    "sprint": (8, 7, 6, 5, 4, 3, 2, 1),
}


@dataclasses.dataclass(frozen=True)
class Session:
    """A points-scoring session: a round's sprint or its Grand Prix."""

    rnd: int
    kind: SessionKind
    name: str  # e.g. "Chinese Grand Prix"


def sessions(year: int) -> list[Session]:
    """Every points-scoring session of `year` in date order, run or not."""
    result = []
    for race in jolpi.get_year_races(year):
        rnd = int(race["round"])
        if "Sprint" in race:
            result.append(Session(rnd, "sprint", race["raceName"]))
        result.append(Session(rnd, "race", race["raceName"]))
    return result


def remaining_after(year: int, session: Session) -> list[Session]:
    """The sessions of `year` that come after `session`, in date order.

    Raises:
        ValueError: If `session` is not in the `year` calendar.
    """
    all_sessions = sessions(year)
    for i, s in enumerate(all_sessions):
        if (s.rnd, s.kind) == (session.rnd, session.kind):
            return all_sessions[i + 1 :]
    msg = f"No {session.kind} in round {session.rnd} of {year}"
    raise ValueError(msg)


def max_points(remaining: list[Session]) -> int:
    """Most points one driver can score in `remaining`: winning every one."""
    return sum(POINTS[session.kind][0] for session in remaining)


def main() -> None:
    """Print what is left of the season after each session run so far."""
    # Imported here, not at the top, as standings imports this module.
    import standings  # noqa: PLC0415

    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    all_sessions = sessions(year)
    races = sum(s.kind == "race" for s in all_sessions)
    print(
        f"{year}: {races} Grands Prix, {len(all_sessions) - races} sprints, "
        f"{max_points(all_sessions)} points available to one driver\n"
    )

    print("After                                   GPs left  Sprints  Max pts")
    for snapshot in standings.standings_by_session(year):
        session = snapshot.session
        remaining = remaining_after(year, session)
        sprints = sum(s.kind == "sprint" for s in remaining)
        label = f"R{session.rnd} {session.name} ({session.kind})"
        print(
            f"{label:40} {len(remaining) - sprints:8} {sprints:8}"
            f" {max_points(remaining):8}"
        )


if __name__ == "__main__":
    main()
