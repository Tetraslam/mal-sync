from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from mal_sync.models import MalCandidate

NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str) -> str:
    title = title.replace("×", "x")
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return " ".join(NON_WORD.sub(" ", title).split())


def title_score(source: str, candidate: str) -> float:
    source_normalized = normalize_title(source)
    candidate_normalized = normalize_title(candidate)
    if source_normalized == candidate_normalized:
        return 1.0
    return SequenceMatcher(None, source_normalized, candidate_normalized).ratio()


def rank_candidates(source_title: str, nodes: list[dict[str, Any]]) -> list[MalCandidate]:
    candidates = []
    for node in nodes:
        alternatives = node.get("alternative_titles") or {}
        titles = [
            node.get("title", ""),
            alternatives.get("en", ""),
            alternatives.get("ja", ""),
            *(alternatives.get("synonyms") or []),
        ]
        score = max((title_score(source_title, title) for title in titles if title), default=0.0)
        candidates.append(
            MalCandidate(
                id=int(node["id"]),
                title=str(node["title"]),
                alternative_titles=tuple(title for title in titles[1:] if title),
                num_episodes=int(node.get("num_episodes") or 0),
                media_type=str(node.get("media_type") or ""),
                status=str(node.get("status") or ""),
                score=round(score, 3),
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
