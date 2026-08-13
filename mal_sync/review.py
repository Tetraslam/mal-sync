from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mal_sync.models import HistorySeries, MalCandidate, MalListEntry, SyncChange


def build_review_item(series: HistorySeries, candidates: list[MalCandidate]) -> dict[str, Any]:
    selected = candidates[0].id if candidates and candidates[0].score >= 0.9 else None
    return {
        "include": True,
        "crunchyroll_id": series.crunchyroll_id,
        "crunchyroll_title": series.crunchyroll_title,
        "season_title": series.season_title,
        "episodes_watched": series.episodes_watched,
        "last_watched_at": series.last_watched_at,
        "mal_id": selected,
        "candidates": [candidate.to_dict() for candidate in candidates[:5]],
    }


def write_review(path: Path, items: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"shows": items}, indent=2) + "\n")


def load_review(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read review file {path}: {error}") from error
    shows = payload.get("shows")
    if not isinstance(shows, list):
        raise TypeError("Review file must contain a `shows` array.")
    return shows


def desired_status(episodes: int, total_episodes: int) -> str:
    return "completed" if total_episodes > 0 and episodes >= total_episodes else "watching"


def build_changes(
    shows: list[dict[str, Any]], current: dict[int, MalListEntry]
) -> tuple[list[SyncChange], list[str]]:
    changes: list[SyncChange] = []
    errors: list[str] = []
    for show in shows:
        if not show.get("include", True):
            continue
        mal_id = show.get("mal_id")
        if not isinstance(mal_id, int) or isinstance(mal_id, bool):
            errors.append(
                f"{show.get('crunchyroll_title', '<untitled>')}: choose a mal_id or exclude it"
            )
            continue
        candidate = next(
            (
                candidate
                for candidate in show.get("candidates", [])
                if candidate.get("id") == mal_id
            ),
            {},
        )
        episodes = int(show.get("episodes_watched") or 0)
        total_episodes = int(candidate.get("num_episodes") or 0)
        if total_episodes > 0:
            episodes = min(episodes, total_episodes)
        new_status = desired_status(episodes, total_episodes)
        old = current.get(mal_id)
        if old and old.episodes_watched > episodes:
            continue
        if old and old.episodes_watched == episodes and old.status == new_status:
            continue
        changes.append(
            SyncChange(
                anime_id=mal_id,
                title=str(candidate.get("title") or show.get("crunchyroll_title")),
                old_status=old.status if old else "not on list",
                old_episodes=old.episodes_watched if old else 0,
                new_status=new_status,
                new_episodes=episodes,
            )
        )
    return changes, errors


def print_changes(changes: list[SyncChange]) -> None:
    if not changes:
        print("MAL is already up to date for the selected shows.")
        return
    print("\nProposed MAL updates:\n")
    for change in changes:
        print(
            f"  {change.title}: {change.old_episodes} ({change.old_status}) -> "
            f"{change.new_episodes} ({change.new_status})"
        )
