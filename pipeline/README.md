# Touchline video tool

Tags a match automatically from the video: kick-off, half-time, second-half kick-off, full-time and goals. Shots and team shape are in development. Work in progress; see **Accuracy** below for where it stands.

## Using it

1. Drag a match video (MP4) onto **`Analyse match.bat`**.
2. Type your team's shirt colour and the opposition's (e.g. `navy`, `red`, `white`).
3. Leave it running, ideally overnight: for now it takes about 2–3 times as long as the video on a computer with an NVIDIA graphics card (speeding this up is on the roadmap). If it stops, run it again; finished steps are skipped.
4. When it says **Done**, open the match in Touchline, load the same video on the Tag screen, press **Add automatic tags** and choose the `.touchline-auto.json` file it made next to the video.

Automatic tags show an **auto** badge in the event log. Check them against the video; you can delete or add tags as normal. Re-adding automatic tags replaces the old automatic ones and keeps everything you tagged by hand.

## Setup (once, Windows)

Needs Python 3.12 and an NVIDIA graphics card (a CPU works but is very slow).

```powershell
cd pipeline
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python -m pip install -r requirements.txt
```

Then download the football models into `pipeline/models/` (from the [Roboflow sports](https://github.com/roboflow/sports) project, MIT-licensed code; weights trained with Ultralytics, AGPL-3.0):

```powershell
.venv\Scripts\gdown -O models/rf-ball.pt "https://drive.google.com/uc?id=1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V"
.venv\Scripts\gdown -O models/rf-pitch.pt "https://drive.google.com/uc?id=1Ma5Kt86tgpdjCTKfum79YMgNnSjcoOyf"
```

The general-purpose YOLO11 model downloads itself on first run.

## How it works

| Step | Module | What it does |
|---|---|---|
| 1 | `track` | Finds people with YOLO11 and follows them with ByteTrack; records each player's shirt colour. |
| 2 | `camera` | Measures how the camera turns and zooms between frames (Veo's follow-cam is a virtual camera inside a fixed panorama, so frames are related by exact homographies). |
| 3 | `pitch` | Finds pitch markings (Roboflow pitch-keypoint model) and works out where the pitch is, using regulation line dimensions. Calibrations are carried to other frames through the camera motion. |
| 4 | `ballpass` | Finds the ball with a football-specific model. |
| 5 | `phases` | Kick-offs (players still, teams in their own halves, then everyone moves), half-time (longest spell without play), full-time, and goals (every other kick-off is a restart after a goal). |
| 6 | `shots` | A fast ball leaving a player's feet, within 35 m of the goal they're attacking, on a path towards the goal mouth. |
| – | `export` | Writes the automatic tags file. |

Tools for development: `probe` (detection rates), `bench` (compare models on frames), `sheet` (contact sheets of frames around a moment), `pseudolabel` (build a training set for a custom ball detector).

## Accuracy

Measured against hand-tagged matches in `groundtruth/`. Targets:

| Event | Target | Current |
|---|---|---|
| Kick-off | within 5 s | 2:25 vs 2:25 (Leeming v La Fammia, full match) |
| Second-half kick-off | within 5 s | 58:56, checked by eye on frames |
| Half-time / full-time | within a minute | 47:46 and 105:17: plausible (45 min + stoppage), not yet checked against a referee's watch |
| Goals | ≥ 95% found, near-zero false goals | not yet measured (final score needed). Goals are only counted after a 30-second pause before the restart; 5 uncertain restarts were listed as "possible goals" for checking |
| Shots | ≥ 80% found, ≤ 20% false | not yet measured with the current version |

### Pitch calibration on follow-cam video: not solved yet

Shot locations (for xG) and team shape need every frame mapped onto the pitch. On Veo follow-cam footage this isn't reliable yet, so the video tool **doesn't produce shots or team shape for now** rather than produce wrong numbers. What was measured on Leeming v La Fammia:

- Frames showing the half nearest the camera calibrate well: pitch markings fit to about 0.3 m.
- At the far end, seen at a grazing angle, the (broadcast-trained) pitch model mislabels markings consistently. It claimed the right-hand penalty box five times as often as the left.
- Carrying a calibration to other frames through the camera motion drifts: about 3 m after a few seconds, 20 m+ after a minute.
- Veo's panorama view can't be downloaded, so follow-cam is the footage everyone has.

Progress since (`rig.py`, `rigfit.py`):

- **The camera model is confirmed.** Solving every keyframe's rotation and zoom jointly (bundle adjustment of a rotating camera, from SIFT matches between neighbouring keyframes) fits the matches to **2 pixels**. Veo's follow-cam really is a camera turning and zooming from a fixed point. Long-range "loop closure" matches need filtering first: unfiltered, false matches wrecked the solve.
- **One calibration for the whole match** maps camera directions to the pitch. Near-box and centre-circle/halfway markings each point the same way to within about 2°, and their averages fit one calibration to 0.8–2.3 m. Far-box markings scatter by ~45°: the pitch model mixes up the two penalty boxes.
- **Current accuracy:** fitted on one part of a 5-minute window and tested on the rest, 46% of stable markings land within 2° (≈3 m on the pitch). The remaining error is mostly the detector placing points loosely along lines, not camera drift.
- **Longer windows don't hold yet.** Over 21 minutes, filtered loop closures (accepted only between keyframes facing the same way and agreeing with the sequential solve: 102 kept, 2,290 rejected) bring the camera solve to 2.1 px, but one pitch calibration no longer fits: ~18° median on held-out frames. Likely cause: focal length and rotation trading off over wide pans (a gauge freedom pairwise matches can't see). Candidates: fix or share the focal-length model, add the pitch lines themselves as constraints, or calibrate in short overlapping windows.

Next: (1) project every marking into every frame from the match-wide calibration to make consistent training labels automatically, (2) fine-tune the pitch model on Veo frames with them, (3) repeat, aiming for ~1 m; then switch shots and team shape on. `touchline_cv.shots`, `.positional`, `.fuse` and `.checkcarry` remain for this work.

Other known limits: shot outcome (saved / off target / blocked) isn't detected, so automatic shots will use an outcome-unknown "Shot" type; which player shot isn't identified; goals found from restarts have no pitch position, so they count for the score but not for xG.

Keep match videos outside the repository; `*.mp4` and `*.mov` are git-ignored as a safety net.

Tried and ruled out (2026-10-13): one shared focal length for all keyframes (3.75 px, still ~20 degrees off over 21 minutes), so zoom/rotation trade-off isn't the main cause. Note: on the 21-minute window the first (sequential-only) solve doesn't move from its starting point (22.9 px); debug the initialisation before more modelling.
