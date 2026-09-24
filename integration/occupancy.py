"""Current per-machine occupancy, rebuilt from the CV service's change stream.

The CV service emits `ZoneStateChange` records (cv-service/occupancy.py) whenever
a reserved treadmill flips empty <-> occupied -- printed by `run.py` and, with
`--json-out`, appended as JSONL. The nudge engine only needs the latest state per
machine, so this module replays those records into a `{machine_id: occupied}`
map. It does not import the CV service: the two services share only this contract.

    tracker = OccupancyTracker()
    tracker.apply_all(read_state_log(STATE_LOG_PATH))
    tracker.machine_occupancy()   # -> {"treadmill-1": True, "treadmill-2": False}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


class OccupancyTracker:
    """Last-write-wins view of each machine's occupancy from a change stream."""

    def __init__(self) -> None:
        self._occupied: dict[str, bool] = {}
        self._since: dict[str, str] = {}

    def apply(self, change: Mapping) -> None:
        machine_id = change["machine_id"]
        self._occupied[machine_id] = bool(change["occupied"])
        self._since[machine_id] = change.get("at", "")

    def apply_all(self, changes: Iterable[Mapping]) -> None:
        for change in changes:
            self.apply(change)

    def machine_occupancy(self) -> dict[str, bool]:
        return dict(self._occupied)

    def occupied(self, machine_id: str) -> "bool | None":
        """True/False if the machine has ever been reported on, else None."""
        return self._occupied.get(machine_id)

    def since(self, machine_id: str) -> "str | None":
        return self._since.get(machine_id) or None


def read_state_log(path: "str | Path") -> list[dict]:
    """Load a `run.py --json-out` JSONL file. Missing file -> empty list."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def occupancy_from_log(path: "str | Path") -> dict[str, bool]:
    tracker = OccupancyTracker()
    tracker.apply_all(read_state_log(path))
    return tracker.machine_occupancy()


def write_state_change(
    path: "str | Path",
    machine_id: str,
    occupied: bool,
    at: "datetime | None" = None,
    *,
    zone_id: str = "",
) -> dict:
    """Append one `ZoneStateChange`-shaped record. Used by the staff dashboard's
    demo controls to puppet the camera; the format matches `run.py --json-out`
    so a replay cannot tell the two apart."""
    at = at or datetime.now().astimezone()
    record = {
        "zone_id": zone_id or f"zone::{machine_id}",
        "machine_id": machine_id,
        "occupied": bool(occupied),
        "at": at.isoformat(),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record
