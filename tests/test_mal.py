from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from mal_sync.mal import MalClient, MalError, search_query


def client_with(handler) -> MalClient:
    client = MalClient(
        "client-id",
        "client-secret",
        "http://localhost:8766/callback",
        Path("unused-token.json"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.token = {"access_token": "token", "expires_at": 9999999999}
    client._pace = lambda: None
    return client


def test_search_query_stays_within_mal_limit_at_word_boundary() -> None:
    query = search_query("word " * 20)
    assert len(query) <= 64
    assert query.endswith("word")


def test_search_sends_bounded_query() -> None:
    requested_query = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_query
        requested_query = parse_qs(request.url.query.decode())["q"][0]
        return httpx.Response(200, json={"data": []}, request=request)

    client_with(handler).search("word " * 20)
    assert len(requested_query) <= 64


def test_invalid_query_returns_no_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "invalid q"}, request=request)

    assert client_with(handler).search("valid title") == []


def test_server_error_is_not_silenced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    with pytest.raises(MalError, match="HTTP 500"):
        client_with(handler).search("valid title")


def test_edge_redirect_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                307,
                headers={"location": "https://myanimelist.net/error.json"},
                request=request,
            )
        return httpx.Response(200, json={"data": []}, request=request)

    monkeypatch.setattr("mal_sync.mal.time.sleep", delays.append)
    assert client_with(handler).search("valid title") == []
    assert calls == 2
    assert delays == [5]
