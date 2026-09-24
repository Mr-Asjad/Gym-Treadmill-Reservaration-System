"""Offline analysis helpers for the CV playground.

Two stages, deliberately split so the UI can tune cheaply:

  run_detection()  -- decode a video, sample frames, run the (expensive) pose
                      detector once. Returns a DetectionRun.
  replay()         -- push those cached pose detections through the anchor +
                      homography + zone + vote + occupancy stages with whatever
                      calibration / zones / debounce you like. Cheap, re-runnable.

Assumes a fixed camera.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

import config
from detector import (
    L_ANKLE,
    L_HIP,
    R_ANKLE,
    R_HIP,
    PoseDetection,
    PoseDetector,
    ScriptedPoseDetector,
    anchor_point,
)
from homography import Homography
from occupancy import ZoneOccupancyMonitor, ZoneStateChange, ZoneStatus
from pipeline import OccupancyPipeline
from smoothing import ZoneAssignmentSmoother
from tracker import CentroidTracker
from zones import Zone

REPLAY_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


@dataclass
class DetectionRun:
    fps: float
    frame_times: list[float]                    # seconds from clip start, per sampled frame
    detections: list[list[PoseDetection]]       # aligned to frame_times
    hip_drop: float = config.HIP_ANCHOR_DROP    # auto-derived ankle-vs-hip y gap
    width: int = 0
    height: int = 0
    frames: "list[bytes] | None" = None         # JPEG preview frames, aligned
    source_name: str = ""

    @property
    def n_frames(self) -> int:
        return len(self.frame_times)

    @property
    def duration(self) -> float:
        return self.frame_times[-1] if self.frame_times else 0.0

    @property
    def detection_count(self) -> int:
        return sum(len(d) for d in self.detections)


def derive_hip_drop(
    detections: "Sequence[Sequence[PoseDetection]]", min_conf: float
) -> float:
    """Median (ankle-midpoint y - hip-midpoint y) over detections where both are
    confident. Falls back to the config default when there are no samples."""
    gaps: list[float] = []
    for frame in detections:
        for det in frame:
            la, ra = det.keypoint(L_ANKLE), det.keypoint(R_ANKLE)
            lh, rh = det.keypoint(L_HIP), det.keypoint(R_HIP)
            if not all(k is not None and k.conf >= min_conf for k in (la, ra, lh, rh)):
                continue
            gaps.append((la.y + ra.y) / 2.0 - (lh.y + rh.y) / 2.0)
    return statistics.median(gaps) if gaps else config.HIP_ANCHOR_DROP


def run_detection(
    video_path: str,
    detector: PoseDetector,
    *,
    every_n: int = 3,
    max_frames: "int | None" = None,
    keep_frames: bool = True,
    preview_width: int = 640,
) -> DetectionRun:
    """Decode `video_path`, run `detector` on every `every_n`-th frame."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video {video_path!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    times: list[float] = []
    dets: list[list[PoseDetection]] = []
    frames: list[bytes] = []
    idx = kept = 0
    pw = ph = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % max(1, every_n) == 0:
                times.append(idx / fps)
                dets.append(list(detector.detect(frame)))
                if keep_frames:
                    h, w = frame.shape[:2]
                    preview = frame
                    if preview_width and w > preview_width:
                        scale = preview_width / w
                        preview = cv2.resize(frame, (preview_width, int(round(h * scale))))
                    ph, pw = preview.shape[:2]
                    frames.append(cv2.imencode(".jpg", preview)[1].tobytes())
                kept += 1
                if max_frames and kept >= max_frames:
                    break
            idx += 1
    finally:
        cap.release()

    return DetectionRun(
        fps=fps,
        frame_times=times,
        detections=dets,
        hip_drop=derive_hip_drop(dets, config.ANKLE_CONF_THRESHOLD),
        width=pw,
        height=ph,
        frames=frames if keep_frames else None,
    )


@dataclass
class ReplayResult:
    changes: list[ZoneStateChange]
    transitions: list[dict] = field(default_factory=list)   # {"t", "machine_id", "occupied"}
    timeline: dict[str, list[bool]] = field(default_factory=dict)
    counts: dict[str, list[int]] = field(default_factory=dict)
    final: dict[str, ZoneStatus] = field(default_factory=dict)


def replay(
    run: DetectionRun,
    zones: "Sequence[Zone]",
    homography: "Homography | None" = None,
    *,
    occupied_after: "float | None" = None,
    vacant_after: "float | None" = None,
    max_distance: "float | None" = None,
    max_disappeared: "int | None" = None,
    zone_margin: "float | None" = None,
    min_kp_conf: "float | None" = None,
    hip_drop: "float | None" = None,
    vote_window: "int | None" = None,
) -> ReplayResult:
    """Re-run occupancy over cached pose detections. Does not touch `run`."""
    pipe = OccupancyPipeline(
        ScriptedPoseDetector(run.detections),
        zones,
        homography=homography if homography is not None else Homography.identity(),
        tracker=CentroidTracker(max_distance, max_disappeared),
        monitor=ZoneOccupancyMonitor(zones, occupied_after, vacant_after),
        smoother=ZoneAssignmentSmoother(vote_window),
        min_kp_conf=min_kp_conf,
        hip_drop=hip_drop if hip_drop is not None else run.hip_drop,
        zone_margin=zone_margin,
    )
    timeline: dict[str, list[bool]] = {z.id: [] for z in zones}
    counts: dict[str, list[int]] = {z.id: [] for z in zones}
    transitions: list[dict] = []
    changes: list[ZoneStateChange] = []

    for t in run.frame_times:
        now = REPLAY_EPOCH + timedelta(seconds=t)
        frame_changes = pipe.process_frame(None, now)
        changes.extend(frame_changes)
        for c in frame_changes:
            transitions.append({"t": t, "machine_id": c.machine_id, "occupied": c.occupied})
        snap = pipe.snapshot()
        for z in zones:
            timeline[z.id].append(snap[z.id].occupied)
            counts[z.id].append(snap[z.id].person_count)

    return ReplayResult(changes, transitions, timeline, counts, pipe.snapshot())


def anchors_for(
    run: DetectionRun,
    homography: Homography,
    *,
    hip_drop: "float | None" = None,
    min_kp_conf: "float | None" = None,
) -> "list[list[dict]]":
    """Per sampled frame, per detection: {'cam': (x, y), 'floor': (x, y)} for the
    feet anchor -- for drawing on the playground's camera + bird's-eye views."""
    hd = hip_drop if hip_drop is not None else run.hip_drop
    mc = min_kp_conf if min_kp_conf is not None else config.ANKLE_CONF_THRESHOLD
    out: list[list[dict]] = []
    for frame in run.detections:
        row: list[dict] = []
        for det in frame:
            a = anchor_point(det, min_kp_conf=mc, hip_drop=hd)
            if a is None:
                continue
            row.append({"cam": a, "floor": homography.project(*a)})
        out.append(row)
    return out


def occupied_seconds(run: DetectionRun, result: ReplayResult) -> dict[str, float]:
    """Per zone, total wall-clock seconds spent 'occupied' across the clip."""
    out: dict[str, float] = {}
    times = run.frame_times
    for zone_id, series in result.timeline.items():
        total = 0.0
        for i in range(1, len(times)):
            if series[i - 1]:
                total += times[i] - times[i - 1]
        out[zone_id] = total
    return out
