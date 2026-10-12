"""Tests for the pipeline's pure functions. Run: .venv\\Scripts\\python -m pytest pipeline/tests"""

import numpy as np
import pytest

from touchline_cv.analyze import hex_to_lab
from touchline_cv.export import build
from touchline_cv.phases import longest_gap
from touchline_cv.pitch import LENGTH, VERTICES, WIDTH, fit_homography, to_pitch


def synthetic_camera():
    """A plausible pitch -> image homography (side-on, elevated view)."""
    return np.array([[12.0, 4.0, 200.0], [0.5, -6.0, 900.0], [0.0005, -0.004, 1.0]])


def project(H, pts):
    v = np.c_[pts, np.ones(len(pts))] @ H.T
    return v[:, :2] / v[:, 2:]


def test_vertices_use_regulation_markings():
    assert VERTICES.shape == (32, 2)
    # Penalty box front edge 16.5 m from the goal line, penalty spot 11 m.
    assert VERTICES[9][0] == pytest.approx(16.5)
    assert VERTICES[8][0] == pytest.approx(11.0)
    assert VERTICES[21][0] == pytest.approx(LENGTH - 11.0)
    # Centre circle points 9.15 m either side of the centre spot.
    assert VERTICES[31][0] - VERTICES[30][0] == pytest.approx(18.3)


def test_fit_recovers_pitch_positions():
    Hpi = synthetic_camera()  # pitch -> image
    idx = np.array([0, 1, 9, 10, 13, 14, 15, 30])  # left box, halfway line, circle
    img = project(Hpi, VERTICES[idx])
    H, inliers, err = fit_homography(img, idx)
    assert inliers == len(idx)
    assert err < 0.01
    # A point never seen by the fit maps to the right place.
    spot = project(Hpi, np.array([[30.0, 20.0]]))[0]
    assert to_pitch(H, *spot) == pytest.approx((30.0, 20.0), abs=0.05)


def test_fit_outvotes_a_mislabelled_point():
    Hpi = synthetic_camera()
    idx = np.array([0, 1, 9, 10, 13, 14, 15, 30])
    img = project(Hpi, VERTICES[idx])
    img[3] += [180, -60]  # one keypoint badly misplaced
    H, inliers, err = fit_homography(img, idx)
    assert inliers == len(idx) - 1
    assert err < 0.05


def test_fit_rejects_collinear_points():
    idx = np.array([13, 14, 15, 16])  # all on the halfway line
    img = project(synthetic_camera(), VERTICES[idx])
    assert fit_homography(img, idx) is None


def test_longest_gap_finds_half_time():
    t = np.arange(0, 6000, 1.0)
    on = np.ones_like(t, dtype=bool)
    on[2800:3400] = False  # 10-minute break
    on[1000:1060] = False  # injury stoppage
    assert longest_gap(t, on, 0, 6000) == (2800.0, 3400.0)


def test_hex_to_lab_orders_lightness():
    assert hex_to_lab("#ffffff")[0] > hex_to_lab("#1b2a4a")[0] > hex_to_lab("#000000")[0]


def test_export_turns_the_last_shot_before_a_goal_into_the_goal():
    phases = {"k1": 145.0, "k2": 3100.0, "ht": 2900.0, "ft": 6000.0, "goals": [{"t": 1000.0, "scored_by": "them"}, {"t": 4000.0, "scored_by": "us"}]}
    shots = [
        {"vt": 900.0, "team": "them", "x": 85.0, "y": 50.0},
        {"vt": 960.0, "team": "them", "x": 88.0, "y": 45.0},
        {"vt": 970.0, "team": "us", "x": 80.0, "y": 50.0},
    ]
    out = build(phases, shots, "match.mp4")
    types = [(e["vt"], e["team"], e["type"], e.get("noloc", False)) for e in out["events"]]
    # Our goal at 4000 s has no shot within 90 s: kept as a goal without a position.
    assert types == [(900.0, "them", "shot", False), (960.0, "them", "goal", False), (970.0, "us", "shot", False), (4000.0, "us", "goal", True)]
    assert out["generator"]["unplaced_goals"] == []
    unknown = build({"k1": 1.0, "goals": [{"t": 50.0, "scored_by": None}]}, [], "m.mp4")
    assert unknown["generator"]["unplaced_goals"] == [{"t": 50.0, "scored_by": None}]
    assert out["sync"] == {"k1": 145.0, "k2": 3100.0, "ht": 2900.0, "ft": 6000.0}
    assert WIDTH == 68.0
