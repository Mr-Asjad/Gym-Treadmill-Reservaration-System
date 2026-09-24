import pytest

from detector import (
    L_ANKLE,
    L_HIP,
    R_ANKLE,
    R_HIP,
    Keypoint,
    ScriptedPoseDetector,
    anchor_point,
    make_pose,
)


def test_make_pose_fills_missing_keypoints_with_zero_confidence():
    d = make_pose((0.0, 0.0, 0.5, 0.9), {L_ANKLE: (0.2, 0.85, 0.9)})
    assert len(d.keypoints) == 17
    assert d.keypoint(L_ANKLE) == Keypoint(0.2, 0.85, 0.9)
    assert d.keypoint(0).conf == 0.0
    assert d.keypoint(99) is None


def test_scripted_pose_detector_replays_then_stops():
    a = make_pose((0.0, 0.0, 1.0, 1.0))
    d = ScriptedPoseDetector([[a], [], [a, a]])
    assert d.detect() == [a]
    assert d.detect() == []
    assert len(d.detect()) == 2
    assert d.exhausted
    assert d.detect() == []


def test_anchor_is_ankle_midpoint_when_both_ankles_are_confident():
    d = make_pose((0, 0, 1, 1), {L_ANKLE: (0.2, 0.80, 0.9), R_ANKLE: (0.4, 0.90, 0.9)})
    assert anchor_point(d, min_kp_conf=0.3, hip_drop=0.1) == pytest.approx((0.3, 0.85))


def test_anchor_is_the_single_confident_ankle():
    d = make_pose((0, 0, 1, 1), {L_ANKLE: (0.2, 0.80, 0.9), R_ANKLE: (0.4, 0.90, 0.1)})
    assert anchor_point(d, min_kp_conf=0.3, hip_drop=0.1) == (0.2, 0.80)


def test_anchor_falls_back_to_hip_midpoint_plus_drop():
    d = make_pose(
        (0, 0, 1, 1),
        {
            L_ANKLE: (0.2, 0.8, 0.05), R_ANKLE: (0.4, 0.9, 0.05),   # occluded
            L_HIP: (0.25, 0.50, 0.9), R_HIP: (0.35, 0.50, 0.9),
        },
    )
    assert anchor_point(d, min_kp_conf=0.3, hip_drop=0.15) == pytest.approx((0.3, 0.65))


def test_anchor_is_none_when_no_keypoint_is_usable():
    d = make_pose((0, 0, 1, 1))
    assert anchor_point(d, min_kp_conf=0.3, hip_drop=0.1) is None
