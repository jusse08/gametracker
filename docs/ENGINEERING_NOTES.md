# Engineering Notes

## Timezone-Aware Datetime Migration

### Current state
- Backend mostly creates timestamps through `utc_now()`, but it still stores naive UTC datetimes for SQLite/SQLModel compatibility.
- Agent still has its own runtime clock paths. Request timestamps are now emitted as aware UTC ISO strings, but local auth expiry state remains integer epoch seconds.
- Pair-rate-limit bookkeeping now uses `time.time()` instead of local naive datetimes.

### Inventory
- Backend models with persisted datetime fields:
  - `users.agent_last_seen_at`
  - `games.created_at`
  - `sessions.started_at`, `sessions.ended_at`
  - `achievements.completed_at`
  - `quest_categories.created_at`
  - `notes.created_at`
  - `agent_config.updated_at`, `pending_launch_requested_at`, `last_launch_at`
  - `agent_pair_codes.expires_at`, `consumed_at`, `created_at`
  - `agent_devices.refresh_expires_at`, `last_seen_at`, `created_at`, `revoked_at`
- Backend serializers already emit ISO strings from these fields in several routers, especially agent endpoints.
- Agent code paths using current time:
  - debug log timestamps in local time for operator readability
  - auth refresh expiry as epoch seconds
  - ping payload timestamps as aware UTC ISO strings

### Risks for full migration
- SQLite does not preserve timezone semantics in a robust native way; SQLModel rows currently assume naive UTC.
- Existing rows are already stored as naive UTC. A partial migration that mixes naive and aware datetimes will create comparison bugs in expiry and heartbeat logic.
- Pydantic/FastAPI parsing will accept aware datetimes from requests, but DB reads are still naive, so round-trips need explicit normalization rules.

### Recommended migration path
1. Keep DB storage as naive UTC in the short term, but centralize all conversions through `app.core.time`.
2. Introduce explicit helpers for `aware UTC -> naive UTC` and `naive UTC -> aware UTC`.
3. Switch API boundary code to normalize inbound/outbound datetimes through these helpers.
4. Add a data audit script that scans for non-UTC assumptions before any schema-level migration.
5. Only then decide whether to keep "naive UTC in SQLite" or migrate to an encoded aware format.

### Tests needed for the migration phase
- Expiry comparisons for pair codes and refresh tokens.
- Agent heartbeat freshness checks around threshold boundaries.
- Session upsert behavior when old rows are naive UTC.
- API round-trip tests for aware timestamps in request/response payloads.

## Frontend State-Store Refactor

### Current data flow
- `library.ts` loads `getGames()` through a small shared cache helper and `getGameProgressSummary()`, while still keeping page-owned filter/render state.
- `game.ts` loads `getGame()` and then fetches checklist, notes, sessions and achievements as separate page-owned slices.
- `add-game.ts` now reuses the shared games cache for deduplication instead of always re-fetching the full list.
- Some mutations already patch local state in place, but many still re-fetch a whole page slice or call `renderGamePage(...)` again.

### Main duplication points
- Game list data is fetched in both library-related flows and detail flows without a shared cache.
- Progress data exists both as aggregated summary in the library and as recomputed detail widgets in the game page.
- Detail-page mutations still mostly do not share a richer common store beyond the new list cache.

### Minimal refactor path
1. Add a tiny shared module for `games list + progress summary + by-id cache`.
2. Let `library.ts` become the primary writer for list-level state after drag-drop and add-game flows.
3. Let `game.ts` hydrate from shared game cache first, then lazily refresh detail-only slices.
4. Replace full `renderGamePage(...)` rerenders after small mutations with targeted cache updates plus local panel refreshes.

### Good first slice
- Shared cache for `Game` entities keyed by `id`.
- One invalidation function for library-level refresh.
- One "update one game in cache" helper used by rating/status/agent-path mutations.

## Live Refresh Reduction

### Current behavior
- Library page polls every 15 seconds with `getGames()` and `getGameProgressSummary()`.
- Game page polls every 10 seconds with `getGame()` plus session history refresh.
- Visibility checks already suppress some unnecessary refreshes while the tab is hidden, and immediate tab-return refreshes now have a small cooldown.
- Agent/WebSocket live flow exists on the backend side, but frontend pages still lean on polling.

### What can be updated locally
- Library status drag-drop already updates local state after `updateGame`.
- Rating updates on game page already update local UI without full page reload.
- Checklist/note/delete/create flows can keep updating local panel state instead of always recomputing via full-page fetch chains.

### What still likely needs polling
- Steam playtime/session history if there is no push source for those updates.
- Agent "currently active" signals until frontend subscribes to a live status feed.

### What should move to live/push later
- Pending agent launch acknowledgements.
- Agent connectivity / heartbeat indicators.
- Library/game agent configuration freshness after backend-side agent actions.

### Low-risk next cuts
- Reuse the same local update pattern for more game-page mutations, instead of falling back to whole-page rerenders.
- Extend the small visibility cooldown pattern into a shared helper instead of duplicating it per page.
- Reuse cached `Game` detail for achievements/progress sections when `sync_type` is already known.
