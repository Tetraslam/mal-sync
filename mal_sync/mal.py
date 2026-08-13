from __future__ import annotations

import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from mal_sync.config import read_json, write_private_json
from mal_sync.matcher import rank_candidates
from mal_sync.models import MalCandidate, MalListEntry


class MalError(RuntimeError):
    pass


def search_query(title: str) -> str:
    query = " ".join(title.split())
    if len(query) <= 64:
        return query
    truncated = query[:64]
    return truncated.rsplit(" ", 1)[0] or truncated


class MalClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_path: Path,
        client: httpx.Client | None = None,
    ):
        if not client_id:
            raise MalError("Missing mal_client_id in config or MAL_CLIENT_ID.")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_path = token_path
        self.client = client or httpx.Client(timeout=30)
        self.token = read_json(token_path)

    def _save_token(self, token: dict[str, Any]) -> None:
        if not token.get("refresh_token") and self.token.get("refresh_token"):
            token["refresh_token"] = self.token["refresh_token"]
        token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600)) - 60
        self.token = token
        write_private_json(self.token_path, token)

    def login(self) -> None:
        verifier = secrets.token_urlsafe(64)[:128]
        state = secrets.token_urlsafe(24)
        redirect = urlparse(self.redirect_uri)
        if redirect.hostname not in {"localhost", "127.0.0.1"} or not redirect.port:
            raise MalError("mal_redirect_uri must be a localhost URL with a port.")

        result: dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(handler) -> None:
                query = parse_qs(urlparse(handler.path).query)
                result["code"] = query.get("code", [""])[0]
                result["state"] = query.get("state", [""])[0]
                handler.send_response(200 if result["code"] else 400)
                handler.send_header("Content-Type", "text/plain")
                handler.end_headers()
                message = (
                    b"MAL authorization complete. You can close this tab.\n"
                    if result["code"]
                    else b"MAL authorization was not completed. Return to the terminal.\n"
                )
                handler.wfile.write(message)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer((redirect.hostname, redirect.port), CallbackHandler)
        server.timeout = 180
        url = "https://myanimelist.net/v1/oauth2/authorize?" + urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "state": state,
                "redirect_uri": self.redirect_uri,
                "code_challenge": verifier,
                "code_challenge_method": "plain",
            }
        )
        print(f"Opening MAL authorization:\n{url}")
        webbrowser.open(url)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        thread.join(timeout=180)
        server.server_close()
        if not result.get("code") or result.get("state") != state:
            raise MalError("MAL authorization timed out or returned an invalid state.")
        response = self.client.post(
            "https://myanimelist.net/v1/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": result["code"],
                "redirect_uri": self.redirect_uri,
                "code_verifier": verifier,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise MalError(
                f"MAL token exchange failed: HTTP {response.status_code}: {response.text[:200]}"
            ) from error
        self._save_token(response.json())

    def _access_token(self) -> str:
        if not self.token.get("access_token"):
            raise MalError("MAL is not authorized. Run `mal-sync login`. ")
        if int(self.token.get("expires_at", 0)) <= time.time():
            response = self.client.post(
                "https://myanimelist.net/v1/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.token.get("refresh_token", ""),
                },
            )
            if response.status_code >= 400:
                raise MalError("MAL token refresh failed. Run `mal-sync login` again.")
            self._save_token(response.json())
        return str(self.token["access_token"])

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {**kwargs.pop("headers", {})}
        headers["Authorization"] = f"Bearer {self._access_token()}"
        response = self.client.request(method, url, headers=headers, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            message = response.text[:300]
            raise MalError(f"MAL request failed: HTTP {response.status_code}: {message}") from error
        return response

    def search(self, title: str, limit: int = 10) -> list[MalCandidate]:
        query = search_query(title)
        if len(query) < 3:
            return []
        try:
            response = self._request(
                "GET",
                "https://api.myanimelist.net/v2/anime",
                params={
                    "q": query,
                    "limit": limit,
                    "fields": "alternative_titles,num_episodes,media_type,status",
                },
            )
        except MalError as error:
            if "HTTP 400" in str(error):
                return []
            raise
        nodes = [item["node"] for item in response.json().get("data", [])]
        return rank_candidates(title, nodes)

    def anime_list(self) -> dict[int, MalListEntry]:
        url = "https://api.myanimelist.net/v2/users/@me/animelist"
        params: dict[str, Any] | None = {"fields": "list_status", "limit": 1000}
        entries: dict[int, MalListEntry] = {}
        while url:
            payload = self._request("GET", url, params=params).json()
            params = None
            for item in payload.get("data", []):
                node = item["node"]
                status = item["list_status"]
                entries[int(node["id"])] = MalListEntry(
                    anime_id=int(node["id"]),
                    title=str(node["title"]),
                    status=str(status["status"]),
                    episodes_watched=int(status["num_episodes_watched"]),
                )
            url = payload.get("paging", {}).get("next", "")
        return entries

    def update(self, anime_id: int, status: str, episodes: int) -> None:
        self._request(
            "PUT",
            f"https://api.myanimelist.net/v2/anime/{anime_id}/my_list_status",
            data={"status": status, "num_watched_episodes": episodes},
        )
