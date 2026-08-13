import base64
import json

from mal_sync.crunchyroll import account_id_from_token, aggregate_history, parse_history_item


def token_with(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_account_id_is_read_from_token() -> None:
    assert account_id_from_token(token_with({"account_id": "abc"})) == "abc"


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
