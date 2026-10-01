"""Shared test setup: no test may reach the real API."""

import pytest

import jolpi


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        msg = f"Test tried to reach the network: {args} {kwargs}"
        raise AssertionError(msg)

    monkeypatch.setattr(jolpi.requests, "get", fail)
