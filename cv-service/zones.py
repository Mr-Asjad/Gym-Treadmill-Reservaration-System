"""Zone definitions -- rectangles in FLOOR coordinates (CLAUDE.md "Zone Detection
Approach"), NOT camera-pixel boxes.

A person's floor position (their ankle anchor, projected through the homography)
is tested against these rectangles with a plain point-in-rectangle check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    machine_id: str
    rect: "tuple[float, float, float, float]"  # (x1, y1, x2, y2) in floor coords

    def __post_init__(self) -> None:
        x1, y1, x2, y2 = self.rect
        if not (x1 < x2 and y1 < y2):
            raise ValueError(f"zone {self.id!r}: rect {self.rect} is not a valid rectangle")

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        x1, y1, x2, y2 = self.rect
        return (x1 - margin) <= x <= (x2 + margin) and (y1 - margin) <= y <= (y2 + margin)

    def depth(self, x: float, y: float) -> float:
        """How far inside the rectangle the point is (negative if outside)."""
        x1, y1, x2, y2 = self.rect
        return min(x - x1, x2 - x, y - y1, y2 - y)


def load_zones(specs: "Iterable[dict] | None" = None) -> "tuple[Zone, ...]":
    specs = config.ZONES if specs is None else specs
    return tuple(
        Zone(s["id"], s["name"], s["machine_id"], tuple(s["rect"])) for s in specs
    )
