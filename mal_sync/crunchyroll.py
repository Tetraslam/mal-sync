from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from typing import Any

import httpx

from mal_sync.models import HistoryEntry, HistorySeries


class CrunchyrollError(RuntimeError):
    pass


def account_id_from_token(token: str) -> str:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, json.JSONDecodeError) as error:
        raise CrunchyrollError(
            "Could not infer the Crunchyroll account ID. Set crunchyroll_account_id in config."
        ) from error
    account_id = claims.get("account_id") or claims.get("etp_user_id") or claims.get("sub")
    if not account_id:
        raise CrunchyrollError(
            "Crunchyroll token has no account ID. Set crunchyroll_account_id in config."
        )
    return str(account_id)


def _integer_episode(value: Any) -> int | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return int(number) if number >= 0 and number.is_integer() else None


def parse_history_item(item: dict[str, Any]) -> HistoryEntry | None:
    panel = item.get("panel") or item
    metadata = panel.get("episode_metadata") or item.get("episode_metadata") or {}
    series_title = metadata.get("series_title") or panel.get("title") or item.get("title")
    episode_number = _integer_episode(metadata.get("episode_number"))
    if not series_title or episode_number is None:
        return None
    return HistoryEntry(
        series_id=str(metadata.get("series_id") or series_title),
        series_title=str(series_title),
        season_title=str(metadata.get("season_title") or ""),
        episode_number=episode_number,
        watched_at=str(item.get("date_played") or item.get("updated_at") or ""),
    )


def aggregate_history(entries: Iterable[HistoryEntry]) -> list[HistorySeries]:
    grouped: dict[tuple[str, str], HistorySeries] = {}
    for entry in entries:
        key = (entry.series_id, entry.season_title)
        previous = grouped.get(key)
        grouped[key] = HistorySeries(
            crunchyroll_id=entry.series_id,
            crunchyroll_title=entry.series_title,
            season_title=entry.season_title,
            episodes_watched=max(
                entry.episode_number, previous.episodes_watched if previous else 0
            ),
            last_watched_at=max(entry.watched_at, previous.last_watched_at if previous else ""),
        )
    return sorted(grouped.values(), key=lambda series: series.last_watched_at, reverse=True)


class CrunchyrollClient:
    def __init__(self, token: str, account_id: str = "", client: httpx.Client | None = None):
        if not token:
            raise CrunchyrollError("Missing crunchyroll_token in config or CRUNCHYROLL_TOKEN.")
        self.token = token.removeprefix("Bearer ").strip()
        self.account_id = account_id or account_id_from_token(self.token)
        self.client = client or httpx.Client(
            base_url="https://www.crunchyroll.com",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "mal-sync/0.1",
            },
            timeout=30,
        )

    def history(self, page_size: int = 100) -> list[HistorySeries]:
        entries: list[HistoryEntry] = []
        page = 1
        cursor = ""
        previous_page_ids: tuple[str, ...] = ()
        while True:
            params = {"page": page, "page_size": page_size, "locale": "en-US"}
            if cursor:
                params["cursor"] = cursor
            response = self.client.get(
                f"/content/v2/{self.account_id}/watch-history",
                params=params,
            )
            if response.status_code == 401:
                raise CrunchyrollError(
                    "Crunchyroll rejected the token. Copy a fresh Bearer token from an authenticated "
                    "watch-history request in your browser's Network panel."
                )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise CrunchyrollError(
                    f"Crunchyroll history request failed: HTTP {response.status_code}"
                ) from error
            payload = response.json()
            items = payload.get("data", [])
            page_ids = tuple(
                str(item.get("id") or item.get("content_id") or item.get("date_played") or item)
                for item in items
            )
            if page_ids and page_ids == previous_page_ids:
                raise CrunchyrollError(
                    "Crunchyroll repeated a history page instead of advancing pagination."
                )
            entries.extend(entry for item in items if (entry := parse_history_item(item)))
            next_cursor = str(
                payload.get("next_cursor") or payload.get("meta", {}).get("next_cursor") or ""
            )
            if not items or (not next_cursor and len(items) < page_size):
                break
            previous_page_ids = page_ids
            cursor = next_cursor
            page += 1
        return aggregate_history(entries)
