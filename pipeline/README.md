# Touchline video pipeline

Turns a match video into Touchline events automatically. Work in progress: the first target is **shots and goals**.

## Setup (Windows)

Needs Python 3.12 and, for reasonable speed, an NVIDIA GPU.

```powershell
cd pipeline
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python -m pip install -r requirements.txt
```

Model weights download automatically on first run and are not committed.

## Tools

- `python -m touchline_cv.probe VIDEO`: samples frames across a match and reports how often players and the ball are detected, saving annotated frames to `pipeline/out/probe/`.

## Accuracy targets

Measured against a hand-tagged match:

| Event | Target |
|---|---|
| Goals | ≥ 95% found, near-zero false goals |
| Shots | ≥ 80% found, ≤ 20% false |
| Shot location | within ~3 m |

Keep match videos outside the repository; `*.mp4` and `*.mov` are git-ignored as a safety net.
