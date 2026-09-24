"""Pose detection + feet anchor extraction (CLAUDE.md "Zone Detection Approach").

`PoseDetector` is the interface the pipeline depends on. `YoloPoseDetector` is
the real backend (lazy-imports ultralytics); `ScriptedPoseDetector` replays fixed
detections for tests and the no-camera demo.

Detections carry a normalized bbox + 17 normalized COCO keypoints -- no identity,
no re-ID (CLAUDE.md "Core Product Decisions").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

import config

# COCO-17 keypoint indices we use.
L_ANKLE, R_ANKLE = 15, 16
L_HIP, R_HIP = 11, 12
N_KEYPOINTS = 17


@dataclass(frozen=True)
class Keypoint:
    x: float          # normalized [0, 1]
    y: float
    conf: float = 0.0


@dataclass(frozen=True)
class PoseDetection:
    bbox: "tuple[float, float, float, float]"   # normalized (x1, y1, x2, y2)
    keypoints: "tuple[Keypoint, ...]"           # 17, COCO order
    confidence: float = 1.0

    def keypoint(self, index: int) -> "Keypoint | None":
        if 0 <= index < len(self.keypoints):
            return self.keypoints[index]
        return None


def make_pose(
    bbox: "Sequence[float]",
    keypoints: "Mapping[int, Sequence[float]] | None" = None,
    confidence: float = 1.0,
) -> PoseDetection:
    """Build a PoseDetection from a bbox and a {coco_index: (x, y, conf)} map;
    unspecified keypoints get confidence 0. Handy for tests and the demo."""
    kp = dict(keypoints or {})
    kps = tuple(
        Keypoint(*kp[i]) if i in kp else Keypoint(0.0, 0.0, 0.0)
        for i in range(N_KEYPOINTS)
    )
    return PoseDetection(tuple(bbox), kps, confidence)


class PoseDetector(Protocol):
    def detect(self, frame) -> "list[PoseDetection]": ...


def anchor_point(
    det: PoseDetection, *, min_kp_conf: float, hip_drop: float
) -> "tuple[float, float] | None":
    """The person's floor position in camera coords: ankle midpoint if the ankle
    keypoints are confident, else hip midpoint dropped by `hip_drop`, else None
    (the detection is skipped this frame)."""
    la, ra = det.keypoint(L_ANKLE), det.keypoint(R_ANKLE)
    ankles = [k for k in (la, ra) if k is not None and k.conf >= min_kp_conf]
    if len(ankles) == 2:
        return ((la.x + ra.x) / 2.0, (la.y + ra.y) / 2.0)
    if len(ankles) == 1:
        return (ankles[0].x, ankles[0].y)

    lh, rh = det.keypoint(L_HIP), det.keypoint(R_HIP)
    hips = [k for k in (lh, rh) if k is not None and k.conf >= min_kp_conf]
    if len(hips) == 2:
        return ((lh.x + rh.x) / 2.0, (lh.y + rh.y) / 2.0 + hip_drop)
    if len(hips) == 1:
        return (hips[0].x, hips[0].y + hip_drop)

    return None


class ScriptedPoseDetector:
    """Replays a fixed list of per-frame PoseDetection lists, then yields nothing."""

    def __init__(self, frames: "Sequence[Sequence[PoseDetection]]") -> None:
        self._frames = [list(f) for f in frames]
        self._i = 0

    def detect(self, frame=None) -> "list[PoseDetection]":
        if self._i >= len(self._frames):
            return []
        out = self._frames[self._i]
        self._i += 1
        return list(out)

    @property
    def exhausted(self) -> bool:
        return self._i >= len(self._frames)


class YoloPoseDetector:
    """YOLOv8-pose. Emits normalized bbox + 17 normalized keypoints per person."""

    def __init__(
        self,
        model_path: "str | None" = None,
        conf_threshold: "float | None" = None,
        model=None,
    ) -> None:
        if model is not None:
            self._model = model
        else:
            try:
                from ultralytics import YOLO
            except ImportError as exc:  # pragma: no cover - needs the heavy dep
                raise RuntimeError(
                    "YoloPoseDetector needs `ultralytics` (pip install -r requirements.txt)"
                ) from exc
            self._model = YOLO(model_path or config.POSE_MODEL)
        self._conf = (
            conf_threshold if conf_threshold is not None else config.PERSON_CONF_THRESHOLD
        )

    def detect(self, frame) -> "list[PoseDetection]":  # pragma: no cover - needs a model
        h, w = frame.shape[:2]
        result = self._model.predict(frame, conf=self._conf, verbose=False)[0]
        if result.keypoints is None or result.boxes is None:
            return []
        xy = result.keypoints.xy         # (n, 17, 2) pixels
        kconf = result.keypoints.conf    # (n, 17) or None
        out: list[PoseDetection] = []
        for i, box in enumerate(result.boxes):
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            kps = tuple(
                Keypoint(
                    float(xy[i][j][0]) / w,
                    float(xy[i][j][1]) / h,
                    float(kconf[i][j]) if kconf is not None else 1.0,
                )
                for j in range(N_KEYPOINTS)
            )
            out.append(
                PoseDetection((x1 / w, y1 / h, x2 / w, y2 / h), kps, float(box.conf[0]))
            )
        return out
