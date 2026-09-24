"""Lightweight centroid tracker.

Assigns short-lived integer ids to person detections across frames by nearest-
centroid matching. Identity is intentionally ephemeral -- we only need "how many
distinct people are in this zone right now", never who they are (CLAUDE.md
"Core Product Decisions").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import config

Box = "tuple[float, float, float, float]"


def _centroid(box: "tuple[float, float, float, float]") -> "tuple[float, float]":
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


@dataclass
class Track:
    id: int
    bbox: "tuple[float, float, float, float]"
    centroid: "tuple[float, float]"
    disappeared: int = 0


class CentroidTracker:
    def __init__(
        self,
        max_distance: "float | None" = None,
        max_disappeared: "int | None" = None,
    ) -> None:
        self.max_distance = (
            max_distance if max_distance is not None else config.TRACKER_MAX_DISTANCE
        )
        self.max_disappeared = (
            max_disappeared
            if max_disappeared is not None
            else config.TRACKER_MAX_DISAPPEARED
        )
        self._next_id = 0
        self._tracks: dict[int, Track] = {}

    def _register(self, box, centroid) -> None:
        self._tracks[self._next_id] = Track(self._next_id, box, centroid)
        self._next_id += 1

    def update(self, boxes: "Sequence[Sequence[float]]") -> "dict[int, tuple]":
        """Feed one frame's detections; return {track_id: bbox} for visible tracks."""
        boxes = [tuple(map(float, b)) for b in boxes]

        if not boxes:
            for tid in list(self._tracks):
                self._tracks[tid].disappeared += 1
                if self._tracks[tid].disappeared > self.max_disappeared:
                    del self._tracks[tid]
            return self._visible()

        centroids = [_centroid(b) for b in boxes]

        if not self._tracks:
            for b, c in zip(boxes, centroids):
                self._register(b, c)
            return self._visible()

        track_ids = list(self._tracks)
        pairs = sorted(
            (math.dist(self._tracks[tid].centroid, ic), ti, ii)
            for ti, tid in enumerate(track_ids)
            for ii, ic in enumerate(centroids)
        )

        matched_tracks: set[int] = set()
        matched_inputs: set[int] = set()
        for dist, ti, ii in pairs:
            if ti in matched_tracks or ii in matched_inputs or dist > self.max_distance:
                continue
            tr = self._tracks[track_ids[ti]]
            tr.bbox, tr.centroid, tr.disappeared = boxes[ii], centroids[ii], 0
            matched_tracks.add(ti)
            matched_inputs.add(ii)

        for ti, tid in enumerate(track_ids):
            if ti not in matched_tracks:
                self._tracks[tid].disappeared += 1
                if self._tracks[tid].disappeared > self.max_disappeared:
                    del self._tracks[tid]

        for ii, (b, c) in enumerate(zip(boxes, centroids)):
            if ii not in matched_inputs:
                self._register(b, c)

        return self._visible()

    def _visible(self) -> "dict[int, tuple]":
        return {tid: t.bbox for tid, t in self._tracks.items() if t.disappeared == 0}
