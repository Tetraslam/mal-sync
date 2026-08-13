from mal_sync.models import HistorySeries, MalCandidate, MalListEntry
from mal_sync.review import build_changes, build_review_item


def show(episodes: int, *, include: bool = True, mal_id: int | None = 1) -> dict:
    return {
        "include": include,
        "crunchyroll_title": "Show",
        "episodes_watched": episodes,
        "mal_id": mal_id,
        "candidates": [{"id": 1, "title": "Show", "num_episodes": 12}],
    }


def test_changes_never_reduce_mal_progress() -> None:
    current = {1: MalListEntry(1, "Show", "watching", 8)}
    changes, errors = build_changes([show(5)], current)
    assert changes == []
    assert errors == []


def test_completed_when_all_episodes_watched() -> None:
    changes, errors = build_changes([show(12)], {})
    assert errors == []
    assert changes[0].new_status == "completed"


def test_equal_progress_can_correct_status() -> None:
    current = {1: MalListEntry(1, "Show", "watching", 12)}
    changes, errors = build_changes([show(12)], current)
    assert errors == []
    assert changes[0].new_status == "completed"


def test_unresolved_included_show_is_an_error() -> None:
    changes, errors = build_changes([show(3, mal_id=None)], {})
    assert changes == []
    assert errors == ["Show: choose a mal_id or exclude it"]


def test_excluded_show_is_ignored() -> None:
    changes, errors = build_changes([show(3, include=False, mal_id=None)], {})
    assert changes == []
    assert errors == []


def test_unresolved_review_item_is_excluded() -> None:
    series = HistorySeries("cr-id", "Show", "Season 1", 3)
    candidate = MalCandidate(1, "Different Show", score=0.5)
    item = build_review_item(series, [candidate])
    assert item["mal_id"] is None
    assert item["include"] is False
