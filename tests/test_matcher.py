from mal_sync.matcher import normalize_title, rank_candidates


def test_normalize_title_preserves_season_and_maps_multiplication_sign() -> None:
    assert normalize_title("SPY × FAMILY Season 2") == "spy x family season 2"


def test_candidates_include_alternative_titles() -> None:
    nodes = [
        {
            "id": 1,
            "title": "Shingeki no Kyojin",
            "alternative_titles": {"en": "Attack on Titan", "synonyms": []},
            "num_episodes": 25,
        }
    ]
    assert rank_candidates("Attack on Titan", nodes)[0].score == 1.0
