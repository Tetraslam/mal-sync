from mal_sync.cli import matching_title


def test_generic_season_title_is_combined_with_series() -> None:
    assert matching_title("Mushoku Tensei", "Season 3") == "Mushoku Tensei Season 3"


def test_descriptive_season_title_is_used_directly() -> None:
    assert matching_title("Show", "Show: The Final Season") == "Show: The Final Season"
