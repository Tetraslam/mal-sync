from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mal-sync"
CONFIG_PATH = CONFIG_DIR / "config.json"
MAL_TOKEN_PATH = CONFIG_DIR / "mal-token.json"


@dataclass(frozen=True)
class Config:
    crunchyroll_token: str = ""
    crunchyroll_account_id: str = ""
    mal_client_id: str = ""
    mal_client_secret: str = ""
    mal_redirect_uri: str = "http://localhost:8766/callback"


def load_config(path: Path = CONFIG_PATH) -> Config:
    values: dict[str, Any] = {}
    if path.exists():
        values = json.loads(path.read_text())

    return Config(
        crunchyroll_token=os.environ.get("CRUNCHYROLL_TOKEN", values.get("crunchyroll_token", ""))
        .removeprefix("Bearer ")
        .strip(),
        crunchyroll_account_id=os.environ.get(
            "CRUNCHYROLL_ACCOUNT_ID", values.get("crunchyroll_account_id", "")
        ).strip(),
        mal_client_id=os.environ.get("MAL_CLIENT_ID", values.get("mal_client_id", "")).strip(),
        mal_client_secret=os.environ.get(
            "MAL_CLIENT_SECRET", values.get("mal_client_secret", "")
        ).strip(),
        mal_redirect_uri=os.environ.get(
            "MAL_REDIRECT_URI",
            values.get("mal_redirect_uri", "http://localhost:8766/callback"),
        ).strip(),
    )


def write_example_config(path: Path = CONFIG_PATH) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "crunchyroll_token": "paste access token here",
                "crunchyroll_account_id": "optional; inferred from token when possible",
                "mal_client_id": "your MAL API client ID",
                "mal_client_secret": "your MAL API client secret",
                "mal_redirect_uri": "http://localhost:8766/callback",
            },
            indent=2,
        )
        + "\n"
    )
    path.chmod(0o600)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.chmod(0o600)
