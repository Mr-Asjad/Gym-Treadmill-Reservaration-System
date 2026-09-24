"""Per-zone occupancy state machine.

Turns a stream of "which tracked people are in which zone this frame" into a
debounced empty/occupied state per zone, with timestamped transitions. This is
the CV service's output contract -- Phase 4's nudge engine reads `snapshot()`
and/or the emitted `ZoneStateChange`s.

Debounce model (fixed camera):

  * A zone goes **occupied** once someone has been present for
    `occupied_after` seconds. Brief detection gaps during that window do NOT
    restart the clock -- only a gap longer than `vacant_after` counts as the
    person having left and resets it.
  * A zone goes **empty** once nobody has been seen for `vacant_after` seconds.

So a single missed YOLO frame (very common when a runner's legs blur or they
lean over the console) never makes the state flicker.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Mapping, Sequence

import config
from zones import Zone


class ZoneState(str, Enum):
    EMPTY = "empty"
    OCCUPIED = "occupied"


@dataclass
class ZoneStatus:
    zone_id: str
    machine_id: str
    state: ZoneState
    since: "datetime | None"          # when the current state began
    last_seen: "datetime | None"      # last frame a person was in the zone
    person_count: int
    first_seen: "datetime | None" = None  # start of the current unbroken presence

    @property
    def occupied(self) -> bool:
        return self.state == ZoneState.OCCUPIED


@dataclass(frozen=True)
class ZoneStateChange:
    zone_id: str
    machine_id: str
    occupied: bool
    at: datetime

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "machine_id": self.machine_id,
            "occupied": self.occupied,
            "at": self.at.isoformat(),
        }


class ZoneOccupancyMonitor:
    def __init__(
        self,
        zones: "Sequence[Zone]",
        occupied_after: "float | None" = None,
        vacant_after: "float | None" = None,
    ) -> None:
        self._occupied_after = timedelta(
            seconds=occupied_after
            if occupied_after is not None
            else config.OCCUPIED_AFTER_SECONDS
        )
        self._vacant_after = timedelta(
            seconds=vacant_after
            if vacant_after is not None
            else config.VACANT_AFTER_SECONDS
        )
        self._status: dict[str, ZoneStatus] = {
            z.id: ZoneStatus(z.id, z.machine_id, ZoneState.EMPTY, None, None, 0)
            for z in zones
        }
        self.changes: list[ZoneStateChange] = []

    def update(
        self, zone_people: "Mapping[str, object]", now: datetime
    ) -> "list[ZoneStateChange]":
        """`zone_people` maps zone_id -> an iterable of person ids seen this frame."""
        emitted: list[ZoneStateChange] = []
        for zid, status in self._status.items():
            if status.since is None:
                status.since = now

            count = len(list(zone_people.get(zid, ())))
            status.person_count = count
            seen = count > 0

            if seen:
                presence_broken = (
                    status.last_seen is None
                    or (now - status.last_seen) > self._vacant_after
                )
                if presence_broken:
                    status.first_seen = now
                status.last_seen = now
            elif (
                status.first_seen is not None
                and status.last_seen is not None
                and (now - status.last_seen) > self._vacant_after
            ):
                status.first_seen = None  # presence lapsed while still empty

            if status.state == ZoneState.EMPTY:
                if (
                    status.first_seen is not None
                    and status.last_seen is not None
                    and (now - status.last_seen) <= self._vacant_after
                    and (now - status.first_seen) >= self._occupied_after
                ):
                    status.state = ZoneState.OCCUPIED
                    status.since = now
                    emitted.append(self._emit(status, True, now))
            else:  # OCCUPIED
                if not seen and (
                    status.last_seen is None
                    or (now - status.last_seen) >= self._vacant_after
                ):
                    status.state = ZoneState.EMPTY
                    status.since = now
                    status.first_seen = None
                    emitted.append(self._emit(status, False, now))

        return emitted

    def _emit(self, status: ZoneStatus, occupied: bool, now: datetime) -> ZoneStateChange:
        change = ZoneStateChange(status.zone_id, status.machine_id, occupied, now)
        self.changes.append(change)
        return change

    def snapshot(self) -> "dict[str, ZoneStatus]":
        return {zid: replace(s) for zid, s in self._status.items()}

    def status(self, zone_id: str) -> ZoneStatus:
        return replace(self._status[zone_id])
