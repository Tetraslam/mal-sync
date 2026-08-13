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

Sign in at <https://www.crunchyroll.com> in Zen, Firefox, Chromium, Chrome, or Brave. `mal-sync fetch` finds that browser session and exchanges it for a short-lived API token automatically. If the token expires during a run, the request is refreshed and retried once.

Set `crunchyroll_browser` to `auto` (the default), `zen`, `firefox`, `chromium`, `chrome`, or `brave`. No Crunchyroll token or account ID belongs in the config. You can use environment variables instead of the config file: `CRUNCHYROLL_BROWSER`, `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET`, and `MAL_REDIRECT_URI`.

Crunchyroll has no public history API. This integration uses its website session and may need updates when Crunchyroll changes its authentication flow.

## Use

```bash
# Fetch all history, query MAL, and create review.json
uv run mal-sync fetch

# Inspect the resulting changes without writing to MAL
uv run mal-sync apply review.json --dry-run

# Preview, confirm, and update MAL
uv run mal-sync apply review.json
```

Each review entry includes the Crunchyroll title and progress, an `include` switch, the selected `mal_id`, and up to five ranked MAL candidates. Automatic selection only happens for high-confidence title matches; unresolved shows default to `"include": false`.

The review file is reusable. A later `fetch` preserves existing matches and manual choices, updates episode progress, and queries MAL only for new or previously failed entries. Requests are paced and retried when MAL throttles them. You can keep the file outside the repository or generate a named snapshot with `mal-sync fetch --output my-history.json`.

## Development

```bash
uv run ruff check .
uv run pytest
```

The Crunchyroll integration is undocumented and may need endpoint or response-field updates when Crunchyroll changes its site.
