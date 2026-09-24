"""Camera-pixel -> top-down floor-plane projection (CLAUDE.md "Zone Detection Approach").

Calibrate once: pick 4 points in the camera image that form a rectangle on the
gym floor (mat corners, floor tape, tile seams). They map to the 4 corners of a
canonical top-down rectangle -- (0, 0) top-left to (aspect, 1) bottom-right.
After that, project any camera point (a runner's ankle) into floor coordinates
and do a trivial, distortion-free point-in-rectangle zone test.

`project()` is pure Python (a 3x3 apply) so the core pipeline needs no numpy;
building a homography from correspondences (`from_quad`) or inverting one needs
numpy, which the calibration UI / runner already have.
"""
from __future__ import annotations

from typing import Sequence

import config

Matrix = "list[list[float]]"
Point = "tuple[float, float]"

_IDENTITY: "list[list[float]]" = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

# order the 4 calibration points are given / stored in
QUAD_ORDER = ("top-left", "top-right", "bottom-right", "bottom-left")


class Homography:
    def __init__(self, matrix: "Sequence[Sequence[float]]", aspect: float = 1.0) -> None:
        self._m = [[float(v) for v in row] for row in matrix]
        self.aspect = float(aspect)

    # -- apply ---------------------------------------------------------
    def project(self, x: float, y: float) -> "tuple[float, float]":
        (a, b, c), (d, e, f), (g, h, i) = self._m
        u = a * x + b * y + c
        v = d * x + e * y + f
        w = g * x + h * y + i
        if abs(w) < 1e-12:
            return (u, v)
        return (u / w, v / w)

    @property
    def matrix(self) -> "list[list[float]]":
        return [row[:] for row in self._m]

    @property
    def is_identity(self) -> bool:
        return self._m == _IDENTITY

    def inverse(self) -> "Homography":
        import numpy as np

        return Homography(np.linalg.inv(np.array(self._m)).tolist(), self.aspect)

    # -- build --------------------------------------------------------
    @classmethod
    def identity(cls) -> "Homography":
        return cls(_IDENTITY, aspect=1.0)

    @classmethod
    def from_quad(
        cls, image_quad: "Sequence[Sequence[float]]", aspect: float = 1.0
    ) -> "Homography":
        """`image_quad`: 4 (x, y) points in normalized camera coords, ordered
        [top-left, top-right, bottom-right, bottom-left] of a floor rectangle."""
        import numpy as np

        if len(image_quad) != 4:
            raise ValueError("image_quad needs exactly 4 points")
        dst = [(0.0, 0.0), (aspect, 0.0), (aspect, 1.0), (0.0, 1.0)]
        rows, rhs = [], []
        for (sx, sy), (dx, dy) in zip(image_quad, dst):
            rows.append([sx, sy, 1, 0, 0, 0, -sx * dx, -sy * dx])
            rhs.append(dx)
            rows.append([0, 0, 0, sx, sy, 1, -sx * dy, -sy * dy])
            rhs.append(dy)
        h = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
        m = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]
        return cls(m, aspect=aspect)

    # -- serialize --------------------------------------------------
    def to_dict(self) -> dict:
        return {"matrix": self.matrix, "aspect": self.aspect}

    @classmethod
    def from_dict(cls, d: dict) -> "Homography":
        return cls(d["matrix"], d.get("aspect", 1.0))


def load_homography() -> Homography:
    """Build the configured homography, or identity (passthrough) if uncalibrated."""
    quad = config.HOMOGRAPHY_IMAGE_QUAD
    if not quad:
        return Homography.identity()
    return Homography.from_quad(quad, config.HOMOGRAPHY_ASPECT)
