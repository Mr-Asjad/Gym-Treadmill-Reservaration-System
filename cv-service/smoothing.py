"""Majority-vote smoothing of per-track zone assignment (CLAUDE.md step 4).

A runner reaching between two machines for a water bottle makes their anchor
point flick across a zone boundary. Require the assignment to win a majority
over a short rolling window before it is passed to the occupancy monitor.
Window size is configurable (`config.ZONE_VOTE_WINDOW`), never hardcoded.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import Mapping

import config


class ZoneAssignmentSmoother:
    def __init__(self, window: "int | None" = None) -> None:
        self.window = max(
            1, window if window is not None else config.ZONE_VOTE_WINDOW
        )
        self._hist: "dict[int, deque]" = {}
        self._idle: "dict[int, int]" = {}

    def update(
        self, raw: "Mapping[int, str | None]"
    ) -> "dict[int, str | None]":
        """`raw` = {track_id: zone_id or None} for this frame. Returns the
        smoothed assignment per track."""
        out: "dict[int, str | None]" = {}
        for track_id, zone_id in raw.items():
            dq = self._hist.get(track_id)
            if dq is None:
                dq = deque(maxlen=self.window)
                self._hist[track_id] = dq
            dq.append(zone_id)
            self._idle[track_id] = 0
            out[track_id] = _vote(dq)

        for track_id in list(self._hist):
            if track_id in raw:
                continue
            self._idle[track_id] = self._idle.get(track_id, 0) + 1
            if self._idle[track_id] > self.window:
                del self._hist[track_id]
                del self._idle[track_id]

        return out


def _vote(history: "deque") -> "str | None":
    ranked = Counter(history).most_common()
    if len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
        return None                       # ambiguous -> claim no zone
    return ranked[0][0]
