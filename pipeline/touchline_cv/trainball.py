"""Train a ball + person detector on a pseudo-labelled set from pseudolabel.py.

Starts from a small pretrained YOLO and fine-tunes at high resolution, since
the ball is only ~6-10 pixels across in Veo footage. The result goes to
pipeline/models/touchline-ball.pt; compare it with the current ball model on
hand-checked frames (bench.py) before switching to it.

    python -m touchline_cv.trainball pipeline/out/balldata [--epochs 60 --imgsz 1280 --batch 8]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

MODELS = Path(__file__).resolve().parents[1] / "models"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--base", default="yolo11s.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    data = Path(args.data_dir) / "data.yaml"
    model = YOLO(args.base)
    res = model.train(
        data=str(data), imgsz=args.imgsz, epochs=args.epochs, batch=args.batch, patience=15,
        project=str((Path(args.data_dir) / "runs").resolve()), name="ball", exist_ok=True,
        # Football-friendly augmentation: no vertical flips (the sky is always up),
        # mild scale changes, mosaic helps with small objects.
        flipud=0.0, fliplr=0.5, scale=0.3, mosaic=1.0, close_mosaic=10, plots=False, verbose=False,
        # Windows: multi-process data loading crashed inside cv2.resize; load in-process.
        workers=args.workers,
    )
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    MODELS.mkdir(exist_ok=True)
    shutil.copy(best, MODELS / "touchline-ball.pt")
    metrics = YOLO(str(best)).val(data=str(data), imgsz=args.imgsz, batch=args.batch, workers=args.workers, verbose=False)
    names = metrics.names
    for i, c in enumerate(metrics.box.ap_class_index):
        print(f"{names[int(c)]}: precision {metrics.box.p[i]:.3f} recall {metrics.box.r[i]:.3f} mAP50 {metrics.box.ap50[i]:.3f}")
    print(f"saved {MODELS / 'touchline-ball.pt'}")


if __name__ == "__main__":
    main()
