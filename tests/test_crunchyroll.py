import base64
import json

import httpx
import pytest

from mal_sync.config import load_config
from mal_sync.crunchyroll import (
    CrunchyrollClient,
    account_id_from_token,
    aggregate_history,
    parse_history_item,
    token_is_usable,
)


def token_with(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_account_id_is_read_from_token() -> None:
    assert account_id_from_token(token_with({"account_id": "abc"})) == "abc"


def test_old_config_placeholders_are_ignored(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "crunchyroll_token": "paste access token here",
                "crunchyroll_account_id": "optional; inferred from token when possible",
                "mal_client_id": "id",
            }
        )
    )
    config = load_config(path)
    assert config.crunchyroll_token == ""
    assert config.crunchyroll_account_id == ""


def test_truncated_token_is_not_used() -> None:
    assert not token_is_usable(token_with({"account_id": "abc"}) + "…")


def test_unauthorized_history_refreshes_token(monkeypatch: pytest.MonkeyPatch) -> None:
    first = token_with({"account_id": "old"})
    refreshed = token_with({"account_id": "new"})
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(401, request=request)
        return httpx.Response(200, json={"data": []}, request=request)

    monkeypatch.setattr("mal_sync.crunchyroll.token_from_browser", lambda browser: refreshed)
    client = CrunchyrollClient(
        first,
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://www.crunchyroll.com"
        ),
    )
    assert client.history() == []
    assert requests[0].url.path.endswith("/old/watch-history")
    assert requests[1].url.path.endswith("/new/watch-history")


def test_history_is_aggregated_per_season() -> None:
    items = [
        {
            "date_played": "2026-01-01",
            "panel": {
                "episode_metadata": {
                    "series_id": "series",
                    "series_title": "Show",
                    "season_title": "Show Season 2",
                    "episode_number": "2",
                }
            },
        },
        {
            "date_played": "2026-01-02",
            "panel": {
                "episode_metadata": {
                    "series_id": "series",
                    "series_title": "Show",
                    "season_title": "Show Season 2",
                    "episode_number": "5.0",
                }
            },
        },
    ]
    entries = [entry for item in items if (entry := parse_history_item(item))]
    result = aggregate_history(entries)
    assert len(result) == 1
    assert result[0].episodes_watched == 5
    assert result[0].last_watched_at == "2026-01-02"
