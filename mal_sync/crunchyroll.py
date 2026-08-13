from __future__ import annotations

import base64
import json
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import browser_cookie3
import httpx

from mal_sync.models import HistoryEntry, HistorySeries


class CrunchyrollError(RuntimeError):
    pass


def token_claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, json.JSONDecodeError) as error:
        raise CrunchyrollError(
            "Could not infer the Crunchyroll account ID. Set crunchyroll_account_id in config."
        ) from error


def account_id_from_token(token: str) -> str:
    claims = token_claims(token)
    account_id = claims.get("account_id") or claims.get("etp_user_id") or claims.get("sub")
    if not account_id:
        raise CrunchyrollError(
            "Crunchyroll token has no account ID. Set crunchyroll_account_id in config."
        )
    return str(account_id)


def token_is_usable(token: str) -> bool:
    if not token or not token.isascii():
        return False
    try:
        expires_at = int(token_claims(token).get("exp", 0))
    except CrunchyrollError:
        return False
    return not expires_at or expires_at > time.time() + 30


def _firefox_cookie_files() -> list[Path]:
    home = Path.home()
    patterns = (
        ".zen/*/cookies.sqlite",
        ".mozilla/firefox/*/cookies.sqlite",
        ".librewolf/*/cookies.sqlite",
    )
    return [path for pattern in patterns for path in home.glob(pattern)]


def _chromium_cookie_files() -> list[Path]:
    home = Path.home()
    patterns = (
        ".config/chromium/*/Cookies",
        ".config/chromium/*/Network/Cookies",
        ".config/google-chrome/*/Cookies",
        ".config/google-chrome/*/Network/Cookies",
        ".config/BraveSoftware/Brave-Browser/*/Cookies",
        ".config/BraveSoftware/Brave-Browser/*/Network/Cookies",
    )
    return [path for pattern in patterns for path in home.glob(pattern)]


def browser_cookie_jars(browser: str = "auto") -> Iterable[tuple[str, Any]]:
    errors: list[str] = []
    if browser in {"auto", "zen", "firefox"}:
        for path in sorted(
            _firefox_cookie_files(), key=lambda item: item.stat().st_mtime, reverse=True
        ):
            try:
                yield (
                    str(path),
                    browser_cookie3.firefox(cookie_file=str(path), domain_name="crunchyroll.com"),
                )
            except Exception as error:  # noqa: BLE001 - backends raise several undocumented errors
                errors.append(f"{path}: {error}")
    if browser in {"auto", "chromium", "chrome", "brave"}:
        for path in sorted(
            _chromium_cookie_files(), key=lambda item: item.stat().st_mtime, reverse=True
        ):
            try:
                yield (
                    str(path),
                    browser_cookie3.chromium(cookie_file=str(path), domain_name="crunchyroll.com"),
                )
            except Exception as error:  # noqa: BLE001 - backends raise several undocumented errors
                errors.append(f"{path}: {error}")
    if errors and browser != "auto":
        raise CrunchyrollError("Could not read browser cookies: " + "; ".join(errors))


def token_from_browser(browser: str = "auto", client: httpx.Client | None = None) -> str:
    http = client or httpx.Client(timeout=30)
    found_session = False
    failures: list[str] = []
    for source, jar in browser_cookie_jars(browser):
        cookies = {cookie.name: cookie.value for cookie in jar}
        etp_rt = cookies.get("etp_rt")
        if not etp_rt:
            continue
        found_session = True
        device_id = cookies.get("device_id") or str(uuid.uuid4())
        response = http.post(
            "https://www.crunchyroll.com/auth/v1/token",
            headers={
                "Authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
                ),
            },
            cookies={**cookies, "device_id": device_id},
            data={
                "grant_type": "etp_rt_cookie",
                "device_id": device_id,
                "device_type": "Firefox on Linux",
            },
        )
        if response.is_success and response.json().get("access_token"):
            return str(response.json()["access_token"])
        failures.append(f"{source}: HTTP {response.status_code}")
    if not found_session:
        raise CrunchyrollError(
            "No logged-in Crunchyroll session was found in Zen, Firefox, Chromium, Chrome, or Brave. "
            "Log in to crunchyroll.com in one of those browsers and try again."
        )
    raise CrunchyrollError(
        "Crunchyroll could not refresh the browser session ("
        + "; ".join(failures)
        + "). Reload crunchyroll.com in the browser and try again."
    )


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
    def __init__(
        self,
        token: str = "",
        account_id: str = "",
        browser: str = "auto",
        client: httpx.Client | None = None,
    ):
        self.browser = browser
        self.configured_account_id = account_id
        self.client = client or httpx.Client(
            base_url="https://www.crunchyroll.com",
            headers={
                "Accept": "application/json",
                "User-Agent": "mal-sync/0.1",
            },
            timeout=30,
        )
        supplied_token = token.removeprefix("Bearer ").strip()
        self._set_token(
            supplied_token if token_is_usable(supplied_token) else self._refresh_token()
        )

    def _set_token(self, token: str) -> None:
        self.token = token
        self.account_id = self.configured_account_id or account_id_from_token(token)
        self.client.headers["Authorization"] = f"Bearer {token}"

    def _refresh_token(self) -> str:
        return token_from_browser(self.browser)

    def _history_page(self, params: dict[str, Any]) -> httpx.Response:
        response = self.client.get(f"/content/v2/{self.account_id}/watch-history", params=params)
        if response.status_code == 401:
            self._set_token(self._refresh_token())
            response = self.client.get(
                f"/content/v2/{self.account_id}/watch-history", params=params
            )
        return response

    def history(self, page_size: int = 100) -> list[HistorySeries]:
        entries: list[HistoryEntry] = []
        page = 1
        cursor = ""
        previous_page_ids: tuple[str, ...] = ()
        while True:
            params = {"page": page, "page_size": page_size, "locale": "en-US"}
            if cursor:
                params["cursor"] = cursor
            response = self._history_page(params)
            if response.status_code == 401:
                raise CrunchyrollError(
                    "Crunchyroll rejected the browser session. Reload crunchyroll.com and try again."
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
