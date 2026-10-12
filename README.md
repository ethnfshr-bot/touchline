# Touchline

Match stats for amateur football, from your own video.

Touchline is a free, open-source tool for amateur 11-a-side teams. Load your match video (a file from your computer, such as an MP4, or a YouTube link), tag events as it plays, and Touchline turns them into:

- **Match reports:** score and xG, an xG race chart, shot map, possession by thirds, field tilt and team stats.
- **Player ratings:** a transparent FotMob-style 0–10 rating for every player, with a player of the match.
- **Season tracking:** totals and per-90s, average rating and form, goals vs xG, results by formation, stats by position played, and team xG with each player on and off the pitch.
- **Exports:** CSV of season stats, and a JSON backup of everything.

It runs entirely in your browser. There's no account and no server, and your data never leaves your device unless you export it.

## Use it

**Online:** open the hosted version at `https://<your-github-username>.github.io/touchline/` (set this once the repo is on GitHub).

**Locally:** you need [Node.js](https://nodejs.org/) 22 or newer.

```bash
git clone https://github.com/<your-github-username>/touchline.git
cd touchline
npm install
npm run dev
```

Then open http://localhost:5173.

### Tagging a match

1. **Squad:** add your players and their usual position. Position matters for ratings: keepers and defenders gain or lose points for goals conceded.
2. **Matches:** create a match (opponent, date, half length, and optionally a YouTube or Veo link).
3. **Tag:** load the video with **Open video file** or a **YouTube link**. It stays pinned at the top while you tag.
   - Pause at kick-off and press **Mark kick-off**; do the same for the second half. The match clock then follows the video, skipping pre-match footage and the half-time break. If you mark them late, events you've already tagged re-time automatically.
   - For each action, pick Us or Them, pick the player, tap where it happened on the pitch, then pick what happened. For shots, flag headers, big chances, penalties and the assister first.
   - Keys: **Space** plays or pauses, and **←/→** skip 5 seconds. Click a minute in the event log to replay that moment.
   - No video handy? Use the manual clock instead.
4. Open **Lineup and formation** to record starters, subs and formation. That gives accurate minutes, ratings by position and on/off splits.
5. **Report** and **Season** update as you go.

Tag the opposition's on-ball actions too, or possession and field tilt will read 100% for you.

### Video sources

- **Files:** anything your browser can play. MP4 with H.264 video works in every browser (Veo downloads are MP4). WebM and most MOV files work too; some phone recordings in HEVC/H.265 don't play in Chrome or Firefox on Windows, so convert those to H.264 with [HandBrake](https://handbrake.fr/). Files play straight from your disk and are never uploaded or copied. Touchline remembers the file name, but you open the file again each session.
- **YouTube:** public or unlisted videos with embedding allowed (YouTube Studio → video → Show more → "Allow embedding"). Private videos can't be embedded. The link is saved with the match, so the video loads automatically next time. Playback uses YouTube's privacy-enhanced (`youtube-nocookie.com`) player.

### Your data

Everything is stored in your browser's IndexedDB. That means:

- Clearing site data, or using a private window, loses it. **Export a JSON backup regularly** (Matches → Your data).
- Data doesn't sync between devices or people. Use export and import to move it. Importing merges by default; tick "Replace everything" to overwrite.

## How the numbers work

**xG:** each shot gets a probability of scoring from a logistic model of distance to goal and the angle of the goal mouth, adjusted for headers (×0.55) and big chances (×1.6, minimum 0.3). Penalties are a flat 0.76. The coefficients are currently hand-tuned; see the roadmap. Code: [`src/engine/xg.js`](src/engine/xg.js).

**Ratings:** every player starts at 6.0 and gains or loses a fixed amount per action (+1.0 per goal, +0.6 per assist, −0.08 per time losing the ball, and so on). Keepers and defenders who play 60+ minutes get +0.4 for a clean sheet or −0.15 per goal conceded (up to 4). Ratings are kept between 3 and 10, and players need 10+ minutes to be rated. All the weights are in one table in [`src/engine/rating.js`](src/engine/rating.js). FotMob's real model is private, so this is an approximation designed to be comparable from match to match for your own team.

Ratings are only as good as the tagging. A player whose actions aren't tagged will sit near 6.0.

## Roadmap

1. ~~Standalone web app with local storage and JSON import/export~~
2. **Trained xG model:** refit the xG model on [StatsBomb open data](https://github.com/statsbomb/open-data).
3. **Calibrated ratings:** regress the rating weights against real FotMob ratings; explore a VAEP-based rating via [socceraction](https://github.com/ML-KULeuven/socceraction).
4. **Video pipeline:** a Python computer-vision pipeline that detects players and the ball in Veo footage and suggests events automatically.

## Contributing

Contributions are welcome, especially from people who play, coach or analyse amateur football. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[GNU AGPL-3.0-or-later](LICENSE). You can use, modify and share Touchline freely. If you distribute a modified version, or run one as a service for other people, you must make your source code available under the same licence.
