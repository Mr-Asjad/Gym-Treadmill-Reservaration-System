# booking-service

Booking data model + scheduler for the Reserved Row system. Runs with **zero
dependency on the CV service** (CLAUDE.md "Architecture").

## Status — Phases 1 & 2 complete

- `models.py` — `Member`, `Machine`, `Booking`, `SlotRequest`, `SlotSuggestion`,
  interval math, and the default 6-treadmill gym (first 2 reserved).
- `config.py` — `SCHEDULER_MODE` (`"simple"` default / `"cpsat"`) plus every
  tunable duration (grace period, nudge window, booking bounds). Env-overridable.
- `scheduler.py` — `SimpleScheduler`: overlap check + greedy earliest-slot
  suggestion. `build_scheduler()` is the one place `SCHEDULER_MODE` is branched;
  `Scheduler` is the Protocol the Phase 5 CP-SAT scheduler must match.
- `store.py` — `InMemoryBookingStore` and `SQLiteBookingStore`, same protocol.
- `events.py` — append-only, timestamped event log (in-memory + optional JSONL).
- `service.py` — `BookingService`: validates (reservable machine, premium
  member, well-formed non-past window within bounds, no overlap), persists,
  logs every accept / cancel / reject. `build_service()` wires a persistent
  SQLite store + JSONL event log for the UI / dashboard / nudge engine.
- `members.py` — `DEFAULT_MEMBERS`, the fixed demo roster (no persistent
  identity system — see CLAUDE.md "Out of Scope").

Phase 2's reservation UI lives in `../booking-ui/` (Streamlit).

## Run

```bash
pip install -r requirements.txt
python demo.py        # book -> reject overlap -> suggest -> cancel
pytest                # unit tests (simple scheduler + both stores)
```

## Switching scheduler mode

```bash
SCHEDULER_MODE=simple pytest      # default
SCHEDULER_MODE=cpsat  python ...  # Phase 5 — needs ortools, not yet implemented
```
