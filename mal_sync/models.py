from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class HistoryEntry:
    series_id: str
    series_title: str
    season_title: str
    episode_number: int
    watched_at: str = ""


@dataclass(frozen=True)
class HistorySeries:
    crunchyroll_id: str
    crunchyroll_title: str
    season_title: str
    episodes_watched: int
    last_watched_at: str = ""


@dataclass(frozen=True)
class MalCandidate:
    id: int
    title: str
    alternative_titles: tuple[str, ...] = ()
    num_episodes: int = 0
    media_type: str = ""
    status: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alternative_titles"] = list(self.alternative_titles)
        return data


@dataclass(frozen=True)
class MalListEntry:
    anime_id: int
    title: str
    status: str
    episodes_watched: int


@dataclass(frozen=True)
class SyncChange:
    anime_id: int
    title: str
    old_status: str
    old_episodes: int
    new_status: str
    new_episodes: int
