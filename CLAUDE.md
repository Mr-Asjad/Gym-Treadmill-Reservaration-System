# CLAUDE.md — Reserved Row: Premium Treadmill Reservation System

This file gives Claude Code context for working on this project. Read this before making changes.

## Project Summary

A gym has 6 treadmills. 2 of them are flagged "Reserved" (premium members only) and can be
booked in advance for timeslots. A computer vision layer watches the 2 reserved treadmills and
compares live occupancy against the active booking to detect no-shows and "wrong person on a
reserved machine" situations, firing a soft nudge notification rather than any hard lockout.

This is a portfolio project. The goal is a small, real, end-to-end system that's demoable in a
2–3 minute video — not a production gym product. Scope discipline matters more than feature count.

## Core Product Decisions (do not silently change these)

- Only 2 machines are reservable. The other 4 are out of scope entirely.
- No facial recognition and no persistent identity database. Occupancy detection only —
  "is a person present in zone X," nothing more. This is a deliberate privacy/scope choice.
- Enforcement is soft only: notifications/nudges, never automatic machine lockout.
- CP-SAT (Google OR-Tools) is used for slot scheduling but must be **configurable/optional** —
  see "CP-SAT Toggle" below. The system must work correctly with a simple interval-overlap
  scheduler when CP-SAT is disabled.

## Architecture

```
booking-service/      # booking data model, interval logic, optional CP-SAT solver
  ├── models.py        # Booking, Machine, Member data classes
  ├── scheduler.py      # simple interval-overlap scheduler (default)
  ├── cpsat_scheduler.py # CP-SAT-based optimal slot suggestion (optional)
  └── config.py         # SCHEDULER_MODE = "simple" | "cpsat"

cv-service/            # webcam-based occupancy detection
  ├── detector.py       # YOLO pose model, extracts ankle keypoints per detected person
  ├── tracker.py        # lightweight tracker (ByteTrack or simple centroid tracker)
  ├── homography.py     # camera-pixel -> top-down floor-plane calibration + point projection
  └── zones.py          # zone definitions as floor-plane rectangles (NOT camera-pixel boxes)

integration/            # the closed loop
  ├── nudge_engine.py    # compares live occupancy vs active bookings, fires nudge/no-show events
  └── occupancy.py       # replays the CV zone-state JSONL into {machine_id: occupied}

api/                    # FastAPI HTTP layer over booking-service + integration
  ├── main.py           # REST + SSE; one BookingService + one NudgeEngine on app.state
  ├── slots.py          # member booking-grid logic
  └── verdict.py        # pure per-machine verdict rules (was dashboard/view.py)

web/                    # member + staff frontend — Vite + React + TS, hand-rolled CSS
  └── src/routes/{book,floor}.tsx   # /  (member grid)   and   /floor  (staff live view)
```

Keep these as separate, independently testable modules. The CV service should be runnable and
testable with zero dependency on the booking service, and vice versa — they only meet in
`integration/nudge_engine.py` (and above it, `api/`). The frontend talks only to `api/`.

## CP-SAT Toggle

CP-SAT is used only for the "suggest optimal/earliest slot across both machines" feature. It is
NOT required for core booking (no-overlap enforcement works fine with simple interval checks).

- `config.py` should expose `SCHEDULER_MODE` (env var or config value): `"simple"` (default) or
  `"cpsat"`.
- When `"simple"`: slot suggestion just linearly scans both machines' timelines for the earliest
  open slot of the requested duration.
- When `"cpsat"`: use OR-Tools CP-SAT to solve for optimal slot assignment (e.g. when multiple
  pending requests exist and we want to minimize total wait time across members, not just
  greedily assign each in order).
- Both modes must produce a *valid* (non-overlapping) schedule. CP-SAT mode is allowed to
  produce a *better* (more optimal) one — that's the point of having it as a togglable step-up.
- Do not let CP-SAT-specific code leak into `models.py`, the CV service, the API, or the
  frontend — it should be swappable without touching anything else.

## Zone Detection Approach (important — do not regress to bbox-overlap)

Early implementation used raw bounding-box overlap against camera-pixel zone rectangles. This
**breaks at side camera angles**: a person's full bbox (head/torso/outstretched arms) can spill
into a neighboring treadmill's zone even though their feet never left their own machine, causing
both zones to falsely read as occupied. Bbox-overlap tests pixel-rectangle intersection, which
has nothing to do with physical floor position — it is the wrong signal and should not be reused
elsewhere in this project (e.g. don't apply it if more zones/machines are added later).

The correct approach, in order of what actually determines occupancy:

1. **Anchor point = feet, not the whole bbox.** Run a pose model (YOLOv8-pose) and use the
   midpoint of the left/right ankle keypoints (COCO indices 15/16) as the person's position.
   If ankle keypoints have low confidence (common once someone's on a treadmill — the console/
   frame occludes feet from a side angle), fall back to the hip-midpoint (keypoints 11/12) with
   a fixed vertical offset, calibrated once from frames where both ankle and hip were visible.
2. **Project that point through a homography, not raw camera pixels.** Calibrate a one-time
   homography (`cv2.findHomography`) mapping 4 known camera-pixel points (e.g. treadmill mat
   corners or floor tape markers) to their real-world top-down floor coordinates. Transform the
   ankle/hip anchor point through this homography before doing any zone test. This removes the
   camera-angle distortion that caused the original bug — zone rectangles should be defined in
   floor coordinates in `zones.py`, not camera-pixel coordinates.
3. **Point-in-rectangle test in floor space**, not bbox-IoU. Once the anchor point is in floor
   coordinates, "which treadmill is this person on" is a trivial point-in-rectangle check.
4. **Temporal smoothing on zone assignment.** Points near a zone boundary (e.g. reaching for a
   water bottle between machines) will flicker frame-to-frame. Require the same zone assignment
   to persist for N consecutive frames (or majority vote over a short rolling window) before
   flipping the occupancy state. Keep N configurable, not hardcoded.

Quick sanity-check alternative (cheaper, lower accuracy — fine for an early smoke test but not
the final approach): using bottom-center-of-bbox instead of full-bbox-overlap approximates foot
position in raw pixel space without needing pose estimation or homography calibration. Useful to
confirm "anchor point choice is the fix" before investing in the full pose + homography pipeline,
but should be replaced by the pose+homography approach for the actual implementation.

## Build Phases (build and test in this order)

1. **Booking data model + simple interval scheduler** — Booking/Machine/Member models, no-overlap
   enforcement, `SCHEDULER_MODE="simple"` working end-to-end with unit tests.
2. **Reservation UI** — member picks machine + time, sees confirmation. Talks to booking-service.
3. **CV occupancy detection** — YOLO-pose + tracker + homography-calibrated floor zones (see
   "Zone Detection Approach" above), outputs empty/occupied state per zone with timestamps. No
   identity/re-ID.
4. **Nudge engine (closed loop)** — compares live CV occupancy to active bookings; fires
   no-show-release after a grace period, fires soft-nudge when a non-reserving occupant is
   present as a reservation is about to start.
5. **CP-SAT scheduler mode** — add `cpsat_scheduler.py`, wire up `SCHEDULER_MODE="cpsat"`,
   verify it's a drop-in swap with the same interface as the simple scheduler.
6. **Staff dashboard + demo** — live status view of both reserved machines, then record the
   demo video (book → simulate wrong occupant → nudge fires → reserving member arrives → clears).

Don't jump ahead to later phases before earlier ones have working tests. Each phase should be
independently demoable.

## Tech Stack

- Python for booking-service, cv-service, integration, and CP-SAT (OR-Tools)
- YOLOv8-pose (ultralytics) for person detection + ankle/hip keypoints; simple centroid tracker
  or ByteTrack for per-zone presence tracking (identity persistence not required — zone occupancy
  is enough); OpenCV (`cv2.findHomography` / `cv2.perspectiveTransform`) for camera-to-floor
  calibration — see "Zone Detection Approach"
- Frontend is FastAPI (`api/`) + Vite/React/TypeScript (`web/`) with a hand-written CSS design
  system — no component library. Members book at `/`, staff watch `/floor` (live via SSE). The
  earlier Streamlit apps (`booking-ui/`, `dashboard/`) were replaced once polish mattered.
- SQLite is sufficient for booking storage — no need for a heavier DB at this scale

## Conventions

- Write unit tests for the booking/scheduler logic (both simple and CP-SAT modes) before wiring
  up UI or CV — this logic is the most interview-relevant part and should be provably correct.
- Keep zone coordinates and grace-period/nudge-window durations in config, not hardcoded in logic.
- Log every nudge/no-show/booking event with a timestamp — this is what produces the "schedule
  adherence %" metric mentioned in the demo plan, and useful debugging trail during development.
- Favor small, runnable increments over large unstructured commits — each phase above should be
  a working state, not just a step toward one.

## Out of Scope (explicitly — do not build unless asked)

- Facial recognition or any persistent per-person identity system
- Automatic machine lockout / hardware actuation
- More than 2 reservable machines
- Multi-machine "routine" scheduling (e.g. booking a sequence of different machine types)
- Payment/membership-tier billing logic