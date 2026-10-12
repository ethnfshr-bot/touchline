# Contributing to Touchline

Thanks for helping. Touchline is built for amateur teams, so contributions from players, coaches and analysts are as valuable as code. Bug reports, tagging-workflow feedback and ideas for better stats all help.

## Ways to help

- **Report a bug or suggest a feature:** open a GitHub issue. For a wrong number, include the events involved (a JSON export of one match is ideal; remove player names if you prefer).
- **Improve the maths:** xG and rating changes are welcome, but they change everyone's numbers, so explain the reasoning and back it with data where possible (see below).
- **Write code:** pick an open issue, or open one first to discuss anything large.

## Development setup

You need Node.js 22+ and Git.

```bash
npm install
npm run dev        # dev server at http://localhost:5173
npm test           # run the test suite once
npm run test:watch # re-run tests on save
npm run build      # production build into dist/
```

## Project layout

```
src/
  engine/    Pure calculation code: no DOM, no storage. Fully unit-tested.
    actions.js   event types, positions, formations
    xg.js        expected-goals model
    stats.js     per-match team and player stats, minutes, involvement
    rating.js    player rating model
    season.js    season aggregation and splits
  storage/
    db.js        IndexedDB persistence
    io.js        versioned JSON export/import
  tagger/    The browser UI: state, views (HTML templates), charts, event handlers
  main.js    entry point
tests/       Vitest tests for engine/ and storage/
prototype/   the original single-file prototype, kept for reference
```

## Guidelines

- **Keep `src/engine/` pure.** Engine functions take data as arguments and return results. They must not touch the DOM, storage or UI state. That's what makes them testable and reusable (for example from the future Python pipeline's output).
- **Test engine changes.** Every change to `src/engine/` needs a test. If you intend to change an existing number, update the test in the same commit and say why in the commit message.
- **Model changes are separate commits.** Don't mix a change to xG or rating behaviour with refactoring, so reviewers can see exactly what moved.
- **Escape user text.** Views build HTML strings. Wrap every user-supplied value (names, opponents, ids from imports) in `esc()`.
- **Don't break old backups.** If you change the shape of stored data, bump `SCHEMA_VERSION` in `src/storage/io.js` and add a migration so older exports still import.
- **No new runtime dependencies** without discussion. The app ships as a small static site.
- **Accessibility:** use real buttons and labels, keep keyboard focus visible, and check both light and dark mode.

## Changing xG or ratings

These numbers are the heart of the project, so the bar is higher:

1. Open an issue describing the change and why.
2. Show the effect on real data (a before/after table on a few tagged matches, or a validation metric such as log loss or calibration for xG).
3. Keep constants named and in one place (`COEF`, `WEIGHTS` and so on), not inline.

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Make your change with tests. Run `npm test` and `npm run build`.
3. Open a pull request describing what changed and how you checked it. CI runs the tests automatically.

By contributing, you agree that your contributions are licensed under the [AGPL-3.0-or-later](LICENSE).
