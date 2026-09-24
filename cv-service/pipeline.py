"""The CV pipeline: frame -> pose -> feet anchor -> floor projection -> zone.

    pipeline = OccupancyPipeline(YoloPoseDetector(), homography=load_homography())
    for timestamp, frame in feed:          # fixed camera
        for change in pipeline.process_frame(frame, timestamp):
            ...  # zone went occupied / empty
    pipeline.snapshot()  # current ZoneStatus per zone

See CLAUDE.md "Zone Detection Approach": anchor = feet (pose), projected through a
homography, tested against floor-space rectangles, with a majority vote on the
per-track zone assignment before the occupancy debounce.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

import config
from detector import PoseDetector, anchor_point
from homography import Homography, load_homography
from occupancy import ZoneOccupancyMonitor, ZoneStateChange, ZoneStatus
from smoothing import ZoneAssignmentSmoother
from tracker import CentroidTracker
from zones import Zone, load_zones, utcnow


def assign_zone(
    zones: "Sequence[Zone]", x: float, y: float, margin: float = 0.0
) -> "str | None":
    """Which floor zone the point (x, y) is in. If it is inside more than one
    (adjacent rects or the margin overlapping them), the zone it sits most deeply
    inside wins -- one person occupies one machine."""
    candidates = [z for z in zones if z.contains(x, y, margin)]
    if not candidates:
        return None
    return max(candidates, key=lambda z: z.depth(x, y)).id


class OccupancyPipeline:
    def __init__(
        self,
        detector: PoseDetector,
        zones: "Sequence[Zone] | None" = None,
        *,
        homography: "Homography | None" = None,
        tracker: "CentroidTracker | None" = None,
        monitor: "ZoneOccupancyMonitor | None" = None,
        smoother: "ZoneAssignmentSmoother | None" = None,
        min_kp_conf: "float | None" = None,
        hip_drop: "float | None" = None,
        zone_margin: "float | None" = None,
    ) -> None:
        self.zones = tuple(zones) if zones is not None else load_zones()
        self.detector = detector
        self.homography = homography if homography is not None else load_homography()
        self.tracker = tracker or CentroidTracker()
        self.monitor = monitor or ZoneOccupancyMonitor(self.zones)
        self.smoother = smoother or ZoneAssignmentSmoother()
        self.min_kp_conf = (
            min_kp_conf if min_kp_conf is not None else config.ANKLE_CONF_THRESHOLD
        )
        self.hip_drop = hip_drop if hip_drop is not None else config.HIP_ANCHOR_DROP
        self.zone_margin = (
            zone_margin if zone_margin is not None else config.ZONE_MARGIN
        )

    def process_frame(
        self, frame, timestamp: "datetime | None" = None
    ) -> "list[ZoneStateChange]":
        now = timestamp or utcnow()

        anchors: list[tuple[float, float]] = []
        for det in self.detector.detect(frame):
            a = anchor_point(det, min_kp_conf=self.min_kp_conf, hip_drop=self.hip_drop)
            if a is not None:
                anchors.append(a)

        # track the anchor point itself (feet move less erratically than a bbox)
        tracks = self.tracker.update([(ax, ay, ax, ay) for ax, ay in anchors])

        raw: dict[int, "str | None"] = {}
        for track_id, box in tracks.items():
            fx, fy = self.homography.project(box[0], box[1])
            raw[track_id] = assign_zone(self.zones, fx, fy, self.zone_margin)

        smoothed = self.smoother.update(raw)

        zone_people: dict[str, set[int]] = {}
        for track_id, zone_id in smoothed.items():
            if zone_id is not None:
                zone_people.setdefault(zone_id, set()).add(track_id)

        return self.monitor.update(zone_people, now)

    def snapshot(self) -> "dict[str, ZoneStatus]":
        return self.monitor.snapshot()
