import json
from pathlib import Path

import pytest
import requests

import jolpi


def _response(status: int, mr_data: dict | None = None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps({"MRData": mr_data or {}}).encode()
    return resp


def _race_data(total: int, races: list[dict]) -> dict:
    return {"total": str(total), "RaceTable": {"Races": races}}


class FakeApi:
    """Stands in for `requests.get`, answering with queued responses."""

    def __init__(self, *responses: requests.Response) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> requests.Response:
        del kwargs
        self.urls.append(url)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jolpi, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(jolpi.time, "sleep", lambda _: None)


def test_results_are_fetched_then_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    race = {"round": "1", "raceName": "Test GP", "Results": []}
    api = FakeApi(_response(200, _race_data(1, [race])))
    monkeypatch.setattr(jolpi.requests, "get", api)

    assert jolpi.get_race_results(2026, 1) == race
    assert jolpi.get_race_results(2026, 1) == race
    assert api.urls == [f"{jolpi.BASE_URL}/2026/1/results/"]
    assert (tmp_path / "2026" / "1" / "results.json").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_empty_responses_are_not_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = FakeApi(
        _response(200, _race_data(0, [])), _response(200, _race_data(0, []))
    )
    monkeypatch.setattr(jolpi.requests, "get", api)

    assert jolpi.get_race_results(2026, 23) is None
    assert jolpi.get_race_results(2026, 23) is None
    assert len(api.urls) == 2
    assert not list(tmp_path.rglob("*.json"))


def test_refresh_bypasses_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    old = {"round": "1", "raceName": "Old"}
    new = {"round": "1", "raceName": "New"}
    api = FakeApi(
        _response(200, _race_data(1, [old])),
        _response(200, _race_data(1, [new])),
    )
    monkeypatch.setattr(jolpi.requests, "get", api)

    jolpi.get_race_results(2026, 1)
    assert jolpi.get_race_results(2026, 1, refresh=True) == new
    assert jolpi.get_race_results(2026, 1) == new


def test_retries_when_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeApi(_response(429), _response(429), _response(200))
    monkeypatch.setattr(jolpi.requests, "get", api)

    assert jolpi._throttled_get("url", {}).status_code == 200
    assert len(api.urls) == 3


def test_gives_up_when_always_throttled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeApi(*[_response(429)] * jolpi._MAX_ATTEMPTS)
    monkeypatch.setattr(jolpi.requests, "get", api)

    with pytest.raises(requests.HTTPError):
        jolpi._throttled_get("url", {})
    assert len(api.urls) == jolpi._MAX_ATTEMPTS


def test_other_http_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeApi(_response(500))
    monkeypatch.setattr(jolpi.requests, "get", api)

    with pytest.raises(requests.HTTPError):
        jolpi._throttled_get("url", {})
    assert len(api.urls) == 1


def test_session_start_uses_utc_time() -> None:
    start = jolpi._session_start({"date": "2026-03-08", "time": "04:00:00Z"})
    assert start.isoformat() == "2026-03-08T04:00:00+00:00"


def test_session_start_without_time_is_midnight_utc() -> None:
    start = jolpi._session_start({"date": "1950-05-13"})
    assert start.isoformat() == "1950-05-13T00:00:00+00:00"
