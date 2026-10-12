# Touchline

**Mission:** be the best open-source app for amateur teams to measure performance accurately. Low-level football is especially prone to bias (memory, opinion, who shouts loudest), so prefer objective, reproducible measurements over subjective judgement, and always show how a number was produced. The end goal is finding tactics and informing strategy, so favour metrics a coach can act on.

Open-source tool for amateur 11-a-side teams: tag events from match video (Veo), get xG, FotMob-style player ratings and season tracking. Runs entirely in the browser; no backend. Licence: AGPL-3.0-or-later.

## Commands

- `npm run dev`: Vite dev server on :5173
- `npm test`: Vitest (must pass before committing)
- `npm run build`: static build to `dist/` (deployed to GitHub Pages by `.github/workflows/pages.yml`)

## Architecture

- `src/engine/`: **pure functions only** (no DOM, storage, or `tagger/` imports). Data in, numbers out. Roster and matches are passed as arguments, never read from globals.
- `src/storage/`: `db.js` (IndexedDB: `matches` store keyed by id, `meta` store with key `roster`), `io.js` (versioned JSON export/import with validation).
- `src/tagger/`: UI. `state.js` holds `store.data` (persisted) and `ui` (transient). Views in `views/` return HTML strings; `render()` replaces `#app`'s innerHTML on every change. All clicks go through one delegated handler in `events.js`, keyed on `data-a` attributes.
- `prototype/touchline.html`: original claude.ai prototype. Reference only, not built.

## Data model

```
Player { id, name, num, pos }          pos ∈ GK | DEF | MID | FWD (squad group)
Match  { id, created, opp, date, comp, half, veo, formation, events[], minutes{pid: n}, lineup{pid: {pos, on, off}}, video? }
Event  { id, t, team, type, x, y, vt?, pid?, ast?, header?, big?, pen? }
Video  { source: 'file'|'youtube', name?, youtubeId?, k1?, k2? }   k1/k2 = video seconds at each kick-off
```

- `vt` is the event's position in the video (seconds), set when tagged with a video loaded. `t` is derived from it via `engine/videotime.js`, and `retimeEvents` recomputes `t` when kick-off marks change.
- The video player (`tagger/video.js`) lives in `#player` inside the sticky header, **outside `#app`**, so `render()` never destroys it. It has two backends (local file via object URL, YouTube IFrame API) behind one interface. When loaded, it drives the clock through `setClockSource`.

- `t` is match time in **seconds**. Displayed minute = `floor(t/60) + 1`.
- `team` is `'us'` or `'them'`. Only `'us'` events carry `pid`/`ast`.
- `type` is a key of `ACT` in `engine/actions.js`.
- Lineup `pos` is a specific position (`POSP`); `GROUP` maps it to GK/DEF/MID/FWD. Blank `on` = starter, blank `off` = played to full time.
- **Coordinates:** `x`, `y` are 0–100 **in the acting team's own frame**: x = 100 is the goal that team attacks. Opposition events are therefore rotated 180° relative to ours. Use `toScreen`/`toFrame` in `tagger/pitch.js` to convert to the 105×68 m SVG, where we always attack right. Stats that compare both teams in one frame (e.g. `thirds`) must flip `them` events with `100 - x`.

## Conventions

- Plain modern JavaScript (ES modules), no framework, no TypeScript. JSDoc on engine functions.
- Model constants (xG `COEF`, rating `WEIGHTS`, thresholds) are named exports. Never inline magic numbers in the models.
- Every user-supplied string in a template goes through `esc()`, **including ids** (imports can contain arbitrary ids).
- Changing the stored data shape means bumping `SCHEMA_VERSION` and adding to `MIGRATIONS` in `storage/io.js`.
- Tests live in `tests/`; shared fixtures in `tests/fixtures.js`. Reference xG values there are pinned to the current hand-tuned model.
- UI copy: plain, friendly English for amateur players and coaches; no jargon without explanation.

## Working agreements

- The engine was ported from the prototype with exact numerical parity (verified on 500 random matches). Behaviour changes to xG or ratings go in **their own commits**, with the test changed in the same commit and the reason in the message.
- Known prototype bugs, to be fixed as separate commits:
  1. `minsOf` gives a player with no lineup entry or minutes override the full match, so a sub tagged once gets 90 minutes.
  2. "Undo last" falls back to removing the chronologically last event, which isn't necessarily the last one tagged.
  3. The rating doesn't scale with minutes played beyond the 10-minute cut-off.

## Roadmap

1. ✅ Standalone app (IndexedDB, JSON import/export, modules, tests, in-app video from files or YouTube).
2. xG trained on StatsBomb open data (Python notebook → export coefficients into `engine/xg.js`, keep the same inputs).
3. Rating calibration: regress `WEIGHTS` against real FotMob ratings; later a VAEP-based rating via socceraction.
4. Python CV pipeline for Veo footage (detection + tracking → suggested events in Touchline's JSON format). Dev machine: RTX 3060 (12 GB VRAM), enough for local inference and fine-tuning YOLO-sized models; Colab only for anything larger.
