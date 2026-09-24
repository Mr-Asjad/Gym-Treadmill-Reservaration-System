"""CP-SAT scheduler mode (CLAUDE.md "CP-SAT Toggle" / Phase 5).

An optional step-up from `SimpleScheduler` with the same `Scheduler` interface,
so `build_scheduler("cpsat")` swaps it in and nothing else changes.

It earns its keep only for *multi-request* slot suggestion. The simple scheduler
assigns each pending request greedily in arrival order, which can hand an early,
unconstrained request a slot that a later, machine-constrained request needed.
CP-SAT instead solves for the machine + start-time assignment that minimises the
**total wait across all requests**, subject to the same non-overlap rules.

Everything else -- feasibility checks (`is_available`) and the trivial
single-request case -- delegates to `SimpleScheduler`; greedy is already optimal
there. OR-Tools is imported lazily and only this module references it (CLAUDE.md:
no CP-SAT code in models.py, the CV service, or the dashboard).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import config
from models import (
    DEFAULT_MACHINES,
    Booking,
    Machine,
    SlotRequest,
    SlotSuggestion,
)
from scheduler import SimpleScheduler, _blocking_intervals


class CpSatScheduler:
    def __init__(self, machines: "Sequence[Machine] | None" = None) -> None:
        machs = tuple(machines) if machines is not None else DEFAULT_MACHINES
        self._machines = machs
        self._reserved_ids = tuple(m.id for m in machs if m.is_reserved)
        self._simple = SimpleScheduler(machs)
        self._time_limit = config.CPSAT_TIME_LIMIT_SECONDS

    def is_available(
        self,
        machine_id: str,
        start: datetime,
        end: datetime,
        existing: "Sequence[Booking]",
        *,
        ignore_booking_id: "str | None" = None,
    ) -> bool:
        return self._simple.is_available(
            machine_id, start, end, existing, ignore_booking_id=ignore_booking_id
        )

    def suggest(
        self,
        requests: "Sequence[SlotRequest]",
        existing: "Sequence[Booking]",
    ) -> list[SlotSuggestion]:
        reqs = list(requests)
        if len(reqs) <= 1:
            return self._simple.suggest(reqs, existing)
        try:
            solved = self._solve(reqs, existing)
        except Exception:
            solved = None
        # A valid schedule always exists; fall back rather than fail.
        return solved if solved is not None else self._simple.suggest(reqs, existing)

    # ------------------------------------------------------------------ CP-SAT
    def _solve(
        self, requests: list[SlotRequest], existing: "Sequence[Booking]"
    ) -> "list[SlotSuggestion] | None":
        from ortools.sat.python import cp_model

        allowed: list[tuple[str, ...]] = [
            tuple(r.machine_ids) if r.machine_ids else self._reserved_ids
            for r in requests
        ]
        machine_ids = sorted({mid for row in allowed for mid in row})

        # Existing active bookings on the machines any request could use.
        raw_busy: list[tuple[str, datetime, datetime]] = []
        for mid in machine_ids:
            for bs, be in _blocking_intervals(mid, existing):
                raw_busy.append((mid, bs, be))

        # Work in integer seconds from a common epoch so every offset is >= 0.
        epoch = min(
            [r.earliest_start for r in requests] + [bs for _, bs, _ in raw_busy]
        )

        def secs(dt: datetime) -> int:
            return int((dt - epoch).total_seconds())

        durations = [max(1, round(r.duration.total_seconds())) for r in requests]
        rel_earliest = [secs(r.earliest_start) for r in requests]

        busy: dict[str, list[tuple[int, int]]] = {}
        for mid, bs, be in raw_busy:
            busy.setdefault(mid, []).append((max(0, secs(bs)), secs(be)))

        existing_end = max([e for ivs in busy.values() for _, e in ivs] + [0])
        # Guaranteed-feasible upper bound: stack every request after everything.
        horizon = max(rel_earliest) + sum(durations) + existing_end + max(durations) + 1

        model = cp_model.CpModel()
        starts: list = []
        assign: list[dict[str, object]] = []

        for i in range(len(requests)):
            starts.append(model.NewIntVar(rel_earliest[i], horizon, f"start_{i}"))
            row = {mid: model.NewBoolVar(f"on_{i}_{mid}") for mid in allowed[i]}
            model.AddExactlyOne(row.values())
            assign.append(row)

        for mid in machine_ids:
            intervals = [
                model.NewOptionalIntervalVar(
                    starts[i], durations[i], starts[i] + durations[i],
                    assign[i][mid], f"iv_{i}_{mid}",
                )
                for i in range(len(requests))
                if mid in assign[i]
            ]
            for j, (bs, be) in enumerate(busy.get(mid, [])):
                intervals.append(
                    model.NewIntervalVar(bs, be - bs, be, f"fixed_{mid}_{j}")
                )
            if len(intervals) > 1:
                model.AddNoOverlap(intervals)

        model.Minimize(
            sum(starts[i] - rel_earliest[i] for i in range(len(requests)))
        )

        solver = cp_model.CpSolver()
        if self._time_limit:
            solver.parameters.max_time_in_seconds = float(self._time_limit)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        out: list[SlotSuggestion] = []
        for i, r in enumerate(requests):
            start_dt = epoch + timedelta(seconds=int(solver.Value(starts[i])))
            mid = next(m for m, lit in assign[i].items() if solver.Value(lit))
            out.append(SlotSuggestion(mid, start_dt, start_dt + r.duration, r))
        return out
