from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mal_sync.config import CONFIG_PATH, MAL_TOKEN_PATH, load_config, write_example_config
from mal_sync.crunchyroll import CrunchyrollClient, CrunchyrollError
from mal_sync.mal import MalClient, MalError
from mal_sync.review import (
    build_changes,
    build_review_item,
    load_review,
    print_changes,
    write_review,
)


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        prog="mal-sync", description="Review Crunchyroll history before syncing it to MAL."
    )
    subparsers = command_parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="create a private example config")
    subparsers.add_parser("login", help="authorize this tool with MAL")
    fetch = subparsers.add_parser("fetch", help="fetch history and create an editable review file")
    fetch.add_argument("--output", type=Path, default=Path("review.json"))
    apply = subparsers.add_parser("apply", help="preview and apply an edited review file")
    apply.add_argument("review", type=Path, nargs="?", default=Path("review.json"))
    apply.add_argument("--yes", action="store_true", help="skip the final confirmation")
    apply.add_argument("--dry-run", action="store_true", help="show updates without changing MAL")
    return command_parser


def mal_client() -> MalClient:
    config = load_config()
    return MalClient(
        config.mal_client_id,
        config.mal_client_secret,
        config.mal_redirect_uri,
        MAL_TOKEN_PATH,
    )


def fetch(output: Path) -> None:
    config = load_config()
    history = CrunchyrollClient(config.crunchyroll_token, config.crunchyroll_account_id).history()
    if not history:
        print("Crunchyroll returned no episode history.")
        return
    mal = mal_client()
    items = []
    for index, series in enumerate(history, 1):
        search_title = series.season_title or series.crunchyroll_title
        print(f"[{index}/{len(history)}] matching {search_title}")
        items.append(build_review_item(series, mal.search(search_title)))
    write_review(output, items)
    unresolved = sum(item["mal_id"] is None for item in items)
    print(f"\nWrote {len(items)} shows to {output} ({unresolved} need a MAL choice).")
    print("Delete unwanted show objects or set `include` to false, then run:")
    print(f"  mal-sync apply {output}")


def apply_review(path: Path, yes: bool, dry_run: bool) -> None:
    mal = mal_client()
    shows = load_review(path)
    changes, errors = build_changes(shows, mal.anime_list())
    if errors:
        print("Resolve these entries in the review file before syncing:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(2)
    print_changes(changes)
    if not changes or dry_run:
        return
    if not yes and input("\nApply these updates to MAL? [y/N] ").strip().lower() != "y":
        print("No changes made.")
        return
    for change in changes:
        mal.update(change.anime_id, change.new_status, change.new_episodes)
        print(f"Updated {change.title}")


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            write_example_config()
            print(f"Created {CONFIG_PATH}")
        elif args.command == "login":
            mal_client().login()
            print(f"MAL token saved to {MAL_TOKEN_PATH}")
        elif args.command == "fetch":
            fetch(args.output)
        elif args.command == "apply":
            apply_review(args.review, args.yes, args.dry_run)
    except (CrunchyrollError, MalError, FileExistsError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
