# mal-sync

Fetch your Crunchyroll watch history, review exactly what belongs on MyAnimeList, then apply only confirmed progress updates.

The workflow is deliberately split in two:

1. `mal-sync fetch` creates an editable `review.json`.
2. Delete unwanted show objects or set `"include": false`.
3. Resolve uncertain matches by choosing a `mal_id` from the included candidates.
4. `mal-sync apply` prints the exact MAL changes and asks before writing anything.

The tool never lowers existing MAL episode progress. It marks a show completed only when the watched episode reaches MAL's known episode count; otherwise it uses `watching`.

## Install

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run mal-sync init
```

This creates `~/.config/mal-sync/config.json` with mode `0600`.

## Credentials

### MyAnimeList

1. Register an API client at <https://myanimelist.net/apiconfig>.
2. Add `http://localhost:8766/callback` as its redirect URI.
3. Put its client ID and secret in the generated config.
4. Run `uv run mal-sync login` and authorize it in the opened browser.

Tokens are refreshed and stored at `~/.config/mal-sync/mal-token.json`.

### Crunchyroll

Crunchyroll has no public history API, so this uses the same authenticated endpoint as its website. To obtain a token:

1. Sign in at <https://www.crunchyroll.com/history>.
2. Open browser developer tools, then the Network panel.
3. Reload and select the request whose URL ends in `/watch-history`.
4. Copy the value after `Bearer ` from its `Authorization` request header into `crunchyroll_token`.

The account ID is normally read from the token. If that fails, copy the ID from the `/content/v2/<account-id>/watch-history` request URL into `crunchyroll_account_id`.

Crunchyroll tokens expire. Fetch a fresh one when the CLI reports a 401. You can use environment variables instead of the config file: `CRUNCHYROLL_TOKEN`, `CRUNCHYROLL_ACCOUNT_ID`, `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET`, and `MAL_REDIRECT_URI`.

## Use

```bash
# Fetch all history, query MAL, and create review.json
uv run mal-sync fetch

# Inspect the resulting changes without writing to MAL
uv run mal-sync apply review.json --dry-run

# Preview, confirm, and update MAL
uv run mal-sync apply review.json
```

Each review entry includes the Crunchyroll title and progress, an `include` switch, the selected `mal_id`, and up to five ranked MAL candidates. Automatic selection only happens for high-confidence title matches.

The review file is reusable. You can keep it outside the repository, edit episode counts manually, or generate a named snapshot with `mal-sync fetch --output my-history.json`.

## Development

```bash
uv run ruff check .
uv run pytest
```

The Crunchyroll integration is undocumented and may need endpoint or response-field updates when Crunchyroll changes its site.
