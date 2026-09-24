"""Configuration for the CV occupancy service.

Runs independently of the booking service (CLAUDE.md "Architecture"). Zone
rectangles, calibration, and every debounce/tracker duration live here, never
hardcoded in logic (CLAUDE.md "Conventions"). Env vars override every value.
"""
from __future__ import annotations

import json
import os


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _i(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _json(name: str, default):
    raw = os.environ.get(name)
    return json.loads(raw) if raw not in (None, "") else default


# Frame source: a webcam index ("0") or a path to a video file.
VIDEO_SOURCE: str = os.environ.get("CV_VIDEO_SOURCE", "0")

# YOLOv8-pose model (person detection + 17 COCO keypoints). Auto-downloads once.
POSE_MODEL: str = os.environ.get("CV_POSE_MODEL", "yolov8n-pose.pt")
PERSON_CONF_THRESHOLD: float = _f("CV_PERSON_CONF", 0.35)

# Anchor point = feet. Ankle keypoints (COCO 15/16) are used when at least this
# confident; otherwise fall back to the hip midpoint (11/12) shifted down by
# HIP_ANCHOR_DROP (normalized frame height). The playground / run_detection
# auto-derive HIP_ANCHOR_DROP from the clip; this is the fallback.
ANKLE_CONF_THRESHOLD: float = _f("CV_ANKLE_CONF", 0.30)
HIP_ANCHOR_DROP: float = _f("CV_HIP_ANCHOR_DROP", 0.12)

# Homography: 4 points in NORMALIZED camera coords forming a rectangle on the
# floor, ordered [top-left, top-right, bottom-right, bottom-left]. They map to a
# canonical top-down rectangle (0,0)-(aspect,1). Empty => identity (uncalibrated:
# floor coords == normalized camera coords). Calibrate in the playground.
HOMOGRAPHY_IMAGE_QUAD: list = _json("CV_HOMOGRAPHY_QUAD", [])
HOMOGRAPHY_ASPECT: float = _f("CV_HOMOGRAPHY_ASPECT", 1.0)

# The 2 reserved treadmills, as rectangles in FLOOR coordinates (NOT camera
# pixels). Placeholder only -- draw them on the bird's-eye view in the playground
# and paste the printed block back here.
ZONES: list[dict] = _json(
    "CV_ZONES",
    [
        {"id": "zone-1", "name": "Reserved Treadmill 1", "machine_id": "treadmill-1",
         "rect": (0.15, 0.50, 0.45, 0.95)},
        {"id": "zone-2", "name": "Reserved Treadmill 2", "machine_id": "treadmill-2",
         "rect": (0.55, 0.50, 0.85, 0.95)},
    ],
)

# Floor-space slack on the zone rectangle for the membership test.
ZONE_MARGIN: float = _f("CV_ZONE_MARGIN", 0.03)

# Frames of majority vote on a track's zone assignment before it is acted on.
ZONE_VOTE_WINDOW: int = _i("CV_ZONE_VOTE_WINDOW", 5)

# Temporal debounce. A zone goes occupied after someone is present this long
# (brief detection gaps within a run don't restart the clock -- see occupancy.py),
# and goes empty after this long with nobody seen.
OCCUPIED_AFTER_SECONDS: float = _f("CV_OCCUPIED_AFTER_SECONDS", 0.3)
VACANT_AFTER_SECONDS: float = _f("CV_VACANT_AFTER_SECONDS", 1.5)

# Centroid tracker (distances are in normalized [0, 1] camera coordinates,
# measured on the anchor point).
TRACKER_MAX_DISTANCE: float = _f("CV_TRACKER_MAX_DISTANCE", 0.12)
TRACKER_MAX_DISAPPEARED: int = _i("CV_TRACKER_MAX_DISAPPEARED", 15)

# Optional JSONL sink for zone state changes (consumed by Phase 4).
STATE_LOG_PATH: str = os.environ.get("CV_STATE_LOG_PATH", "")
