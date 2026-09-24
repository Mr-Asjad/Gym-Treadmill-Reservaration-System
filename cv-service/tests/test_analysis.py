import numpy as np
import pytest

from analysis import (
    DetectionRun,
    anchors_for,
    derive_hip_drop,
    occupied_seconds,
    replay,
    run_detection,
)
from detector import L_ANKLE, L_HIP, R_ANKLE, R_HIP, ScriptedPoseDetector, make_pose
from homography import Homography
from zones import load_zones


def on_zone_1():
    # ankle midpoint (0.30, 0.80) -> default zone-1
    return make_pose((0.2, 0.3, 0.4, 0.85),
                     {L_ANKLE: (0.28, 0.80, 0.9), R_ANKLE: (0.32, 0.80, 0.9)})


def make_run(frames, dt=0.1, hip_drop=0.12):
    return DetectionRun(
        fps=1 / dt,
        frame_times=[i * dt for i in range(len(frames))],
        detections=frames,
        hip_drop=hip_drop,
    )


def test_replay_reports_transitions_and_timeline():
    frames = [[]] * 3 + [[on_zone_1()]] * 8 + [[]] * 20
    run = make_run(frames)
    result = replay(run, load_zones(), occupied_after=0.2, vacant_after=0.5)

    seq = [(r["machine_id"], r["occupied"]) for r in result.transitions]
    assert seq == [("treadmill-1", True), ("treadmill-1", False)]
    assert len(result.timeline["zone-1"]) == run.n_frames
    assert not result.timeline["zone-2"][-1]
    assert result.final["zone-1"].occupied is False


def test_replay_is_pure_and_repeatable():
    run = make_run([[on_zone_1()]] * 6)
    a = replay(run, load_zones(), occupied_after=0.2, vacant_after=0.5)
    b = replay(run, load_zones(), occupied_after=0.2, vacant_after=0.5)
    assert a.transitions == b.transitions
    assert len(run.detections) == 6            # untouched


def test_replay_applies_the_homography():
    # anchor at camera-x 0.30; identity -> zone-1, shift +0.4 -> zone-2
    frames = [[on_zone_1()]] * 6
    run = make_run(frames)
    ident = replay(run, load_zones(), occupied_after=0.0, vacant_after=0.0)
    shifted = replay(
        run, load_zones(),
        Homography([[1.0, 0.0, 0.40], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        occupied_after=0.0, vacant_after=0.0,
    )
    assert ident.timeline["zone-1"][-1] and not ident.timeline["zone-2"][-1]
    assert shifted.timeline["zone-2"][-1] and not shifted.timeline["zone-1"][-1]


def test_derive_hip_drop_is_the_median_ankle_hip_gap():
    dets = [[
        make_pose((0, 0, 1, 1), {
            L_ANKLE: (0.3, 0.90, 0.9), R_ANKLE: (0.3, 0.90, 0.9),
            L_HIP: (0.3, 0.50, 0.9), R_HIP: (0.3, 0.50, 0.9),
        })
    ]]
    assert derive_hip_drop(dets, 0.3) == pytest.approx(0.40)
    assert derive_hip_drop([[make_pose((0, 0, 1, 1))]], 0.3) == pytest.approx(0.12)  # fallback


def test_occupied_seconds_matches_presence():
    frames = [[on_zone_1()]] * 10 + [[]] * 10        # 0.1s steps => ~0.9s occupied
    run = make_run(frames)
    result = replay(run, load_zones(), occupied_after=0.0, vacant_after=0.0)
    secs = occupied_seconds(run, result)
    assert secs["zone-1"] == pytest.approx(0.9, abs=0.15)
    assert secs["zone-2"] == 0.0


def test_anchors_for_returns_camera_and_floor_points():
    run = make_run([[on_zone_1()], []])
    rows = anchors_for(run, Homography.identity())
    assert rows[0][0]["cam"] == pytest.approx((0.30, 0.80))
    assert rows[0][0]["floor"] == pytest.approx((0.30, 0.80))
    assert rows[1] == []


def test_run_detection_samples_and_encodes_frames(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = str(tmp_path / "clip.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 240))
    if not writer.isOpened():
        pytest.skip("no working VideoWriter backend")
    for _ in range(30):
        writer.write(np.zeros((240, 320, 3), np.uint8))
    writer.release()

    scripted = ScriptedPoseDetector([[on_zone_1()]] * 10)     # 30 / every_n=3
    run = run_detection(path, scripted, every_n=3, preview_width=160)

    assert run.n_frames == 10
    assert run.frame_times == sorted(run.frame_times)
    assert all(isinstance(b, (bytes, bytearray)) for b in run.frames)
    decoded = cv2.imdecode(np.frombuffer(run.frames[0], np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None and decoded.shape[1] == 160
