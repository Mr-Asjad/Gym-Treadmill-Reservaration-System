# Session 1 handoff — Reserved Row

Context dump for starting a fresh chat. Everything here reflects the repo state at
end of session 1 (2026-09-03).

---

## Project

**Reserved Row** — premium treadmill reservation system. Portfolio project,
demoable in a 2–3 min video. A gym has 6 treadmills; 2 are "Reserved" (premium
members book timeslots). A CV layer watches those 2 machines and compares live
occupancy against the active booking to fire **soft nudges** (no lockout) for
no-shows / wrong-person-on-machine.

**Read `CLAUDE.md` first** — it is the source of truth for product decisions,
architecture, build phases, and the CV "Zone Detection Approach". The user edits
it; treat it as authoritative and never silently deviate.

Not a git repo. Platform: Windows 11, PowerShell primary shell (Bash tool also
available). Python 3.11.

---

## Status by phase

| Phase | State | Where |
|---|---|---|
| 1. Booking data model + simple scheduler | **DONE** — 50 tests | `booking-service/` |
| 2. Reservation UI | **DONE** | `booking-ui/` |
| 3. CV occupancy detection | **DONE** — 53 tests (rebuilt to pose+homography) | `cv-service/` |
| 4. Nudge engine (closed loop) | not started | `integration/nudge_engine.py` |
| 5. CP-SAT scheduler mode | not started | `booking-service/cpsat_scheduler.py` |
| 6. Staff dashboard + demo | not started | `dashboard/app.py` |

`integration/` and `dashboard/` are empty folders.

---

## Phase 1 — booking-service (DONE, 50 tests)

Pure standard library. Run tests: `cd booking-service && python -m pytest`.

| File | Role |
|---|---|
| `models.py` | `Member`, `Machine`, `Booking`, `SlotRequest`, `SlotSuggestion`, `BookingStatus`; `intervals_overlap`, `utcnow`/`to_utc` (tz-aware UTC everywhere); `DEFAULT_MACHINES` (6 treadmills, first 2 `is_reserved`) |
| `config.py` | `SCHEDULER_MODE` (`"simple"`/`"cpsat"`), `GRACE_PERIOD`, `NUDGE_WINDOW`, `MIN/MAX_BOOKING_DURATION` (10–90 min), `SLOT_MINUTES`=30, `OPEN_HOUR`=6, `CLOSE_HOUR`=22, `DB_PATH`, `EVENT_LOG_PATH` — all env-overridable |
| `scheduler.py` | `SimpleScheduler` (overlap check + greedy earliest-slot scan). `Scheduler` Protocol = the interface Phase 5 CP-SAT must match. `build_scheduler()` is the ONLY place `SCHEDULER_MODE` is branched |
| `store.py` | `InMemoryBookingStore` + `SQLiteBookingStore`, same `BookingStore` protocol; `SQLiteBookingStore(path, check_same_thread=)` |
| `events.py` | `EventLog` — append-only timestamped events (in-memory + optional JSONL); `EventType` enum |
| `service.py` | `BookingService` — validates (reservable machine, premium member, tz-aware non-past window in bounds, no overlap), persists, logs every accept/cancel/reject. Typed `BookingError` subclasses with `.code`. `build_service(db_path, event_log_path, ...)` = the wired factory used by UI / dashboard / nudge engine |
| `members.py` | `DEFAULT_MEMBERS` — fixed demo roster (3 premium, 1 basic). No persistent identity system (deliberate) |
| `demo.py` | book → reject overlap → suggest → cancel |

Gotcha fixed: `EventLog.__len__` makes an empty log falsy → use `x is not None`
checks, not `x or default`, when wiring optional deps in `BookingService`.

---

## Phase 2 — booking-ui (DONE)

Streamlit. `cd booking-ui && pip install -r requirements.txt && streamlit run app.py`.

- `app.py` — **dead-simple slot grid**: pick member + Today/Tomorrow, then a
  grid of 30-min slots × 2 reserved treadmills. Every cell is one button: Book /
  "You — Cancel" / other member's name / "—" (past). Plus "⚡ Book my next free
  slot". No date/time/duration pickers. One-line flash for success/error.
- `_bootstrap.py` — puts `booking-service/` on `sys.path` (hyphenated folder name
  isn't importable) and creates top-level `data/`.
- State persists to `data/bookings.db` + `data/events.jsonl` (shared with future
  dashboard / nudge engine). Service cached with `st.cache_resource`
  (`check_same_thread=False`).
- Grid shape (slot length, open/close hours) comes from `booking-service/config.py`.

---

## Phase 3 — cv-service (DONE, 53 tests) — **rebuilt this session**

### History (why it looks the way it does)

Went through several iterations before the current design:
1. YOLO **person** detection + **camera-pixel** zone rectangles + bbox
   bottom-centre anchor + centroid tracker + occupancy monitor.
2. Added playground (video upload, live tuning, cached detection).
3. Fine-tuning: user decided pretrained is enough — **not built**.
4. Camera-motion stabilization: built then **removed** — made things worse,
   user rejected. **Fixed camera is assumed.**
5. Debounce rework: presence-with-gap-tolerance (a missed detection frame
   mid-run does NOT restart the occupied clock); defaults cut to 0.3s / 1.5s.
6. One-person-one-zone (deepest containment) so a wide bbox doesn't occupy both.
7. **Camera-pixel zones + bbox anchor still broke at side angles** (bent-over
   runner's bbox spills into the next lane → both machines occupied). User then
   rewrote `CLAUDE.md` with a "Zone Detection Approach" section mandating a new
   design, and we **rebuilt** to it.

### Current design (per CLAUDE.md "Zone Detection Approach")

```
frame
 → YOLOv8-pose ............ PoseDetection: bbox + 17 COCO keypoints (normalized)
 → anchor_point() ......... feet = ankle midpoint (kp 15/16) if confident;
                            else hip midpoint (kp 11/12) + auto-derived drop;
                            else None (detection skipped this frame)
 → CentroidTracker ........ tracks the anchor POINT (feet move less than a bbox)
 → Homography.project() ... anchor (normalized camera) → flattened top-down FLOOR
 → assign_zone() .......... point-in-rectangle in FLOOR space; if in >1 zone,
                            deepest-containment wins (one person → one machine)
 → ZoneAssignmentSmoother . rolling majority vote of each track's zone over N
                            frames (ties → no zone); absorbs boundary flicker
 → ZoneOccupancyMonitor ... debounce → empty/occupied + timestamped changes
```

### Decisions locked in with the user

- **Floor coords = canonical top-down rectangle.** Click 4 floor points → unit
  rect × aspect. No real-world measurements.
- **Pose-only.** The old bbox-bottom "smoke test" mode was removed entirely.
- **Playground = bird's-eye editing.** The top-down view is **synthesised from
  the one existing side-angle camera** via `cv2.warpPerspective` — NOT a second /
  overhead camera. User clicks 4 points forming a real floor rectangle.
- Uncalibrated (`HOMOGRAPHY_IMAGE_QUAD = []`) → identity homography (floor ==
  camera coords) so tests / demo / a roughly-overhead camera still work.

### File inventory

| File | Role |
|---|---|
| `config.py` | `POSE_MODEL="yolov8n-pose.pt"`, `PERSON_CONF_THRESHOLD`, `ANKLE_CONF_THRESHOLD`=0.30, `HIP_ANCHOR_DROP`=0.12 (fallback), `HOMOGRAPHY_IMAGE_QUAD=[]`, `HOMOGRAPHY_ASPECT`=1.0, `ZONES` (**floor** rects, placeholder), `ZONE_MARGIN`=0.03, `ZONE_VOTE_WINDOW`=5, `OCCUPIED_AFTER_SECONDS`=0.3, `VACANT_AFTER_SECONDS`=1.5, tracker vals. All env-overridable |
| `homography.py` | `Homography(matrix, aspect)` — `project(x,y)` (pure Python 3×3), `inverse()` (numpy), `from_quad(image_quad, aspect)` (numpy 8×8 DLT solve; quad order = TL,TR,BR,BL), `identity()`, `to_dict`/`from_dict`, `is_identity`. `load_homography()` reads config (identity if quad unset). `QUAD_ORDER` constant |
| `detector.py` | `Keypoint(x,y,conf)`, `PoseDetection(bbox, keypoints[17], confidence)` + `.keypoint(i)`, `make_pose(bbox, {coco_idx:(x,y,conf)})` factory, `PoseDetector` Protocol, `ScriptedPoseDetector`, `YoloPoseDetector` (lazy ultralytics, accepts preloaded `model=`), `anchor_point(det, *, min_kp_conf, hip_drop)`, COCO consts `L_ANKLE=15 R_ANKLE=16 L_HIP=11 R_HIP=12` |
| `tracker.py` | `CentroidTracker` — **unchanged** from earlier phases. Now fed `(ax,ay,ax,ay)` degenerate boxes at the anchor |
| `smoothing.py` | `ZoneAssignmentSmoother(window)` — `update({tid: zone_id|None}) → {tid: zone_id|None}`, per-track rolling deque majority vote, tie → `None`, prunes tracks unseen for `window` frames |
| `zones.py` | `Zone(id, name, machine_id, rect)` — `rect` is **floor coords** (validation only checks `x1<x2, y1<y2` — no [0,1] clamp). `contains(x,y,margin=0)`, `depth(x,y)`. `load_zones()`, `utcnow()` |
| `occupancy.py` | `ZoneOccupancyMonitor` — **unchanged**. Presence-with-gap-tolerance debounce. `ZoneStatus`, `ZoneStateChange` (`.to_dict()`), `snapshot()`, `status(id)` |
| `pipeline.py` | `OccupancyPipeline(detector, zones=None, *, homography, tracker, monitor, smoother, min_kp_conf, hip_drop, zone_margin)`; `assign_zone(zones, x, y, margin) → str|None` |
| `analysis.py` | `DetectionRun` (`.detections: list[list[PoseDetection]]`, `.hip_drop`), `run_detection(video, detector, *, every_n, max_frames, ...)`, `replay(run, zones, homography=None, *, occupied_after, vacant_after, max_distance, zone_margin, min_kp_conf, hip_drop, vote_window) → ReplayResult`, `anchors_for(run, homography, *, hip_drop, min_kp_conf)`, `derive_hip_drop(dets, min_conf)`, `occupied_seconds(run, result)`. `REPLAY_EPOCH` |
| `pipeline` split | detection is expensive/cached; `replay` re-runs everything else instantly (calibration, zones, debounce, vote = cheap tuning) |
| `feed.py` | `VideoFeed(source)` — webcam idx or file path, yields `(utcnow(), frame)`. Lazy cv2 |
| `run.py` | CLI: `--source`, `--show`, `--json-out`. Loads `YoloPoseDetector` + `load_homography()` + floor `load_zones()`. `_draw` projects zone rects back to camera pixels via `homography.inverse()` and draws polygons |
| `demo.py` | Scripted `PoseDetection`s + `Homography.identity()`; person on treadmill-1 → OCCUPIED at +0.5s, EMPTY at +8s. No camera / no weights |
| `playground.py` | Streamlit, 3 stages (see below) |

### Playground flow (`streamlit run playground.py`)

Needs `streamlit-image-coordinates` (hard requirement now; in requirements.txt).

1. **Sidebar**: upload; detection sliders (conf/every_n/max_frames — re-run pose);
   occupancy sliders (occupied/vacant/vote_window/zone_margin/ankle_conf/hip_drop/
   tracker — instant replay).
2. **Stage 1 — Calibrate**: click 4 floor-rectangle corners (TL→TR→BR→BL) on a
   reference frame; set aspect. Warped bird's-eye view appears. "Reset calibration".
3. **Stage 2 — Draw zones**: radio treadmill-1/2, drag a box on the bird's-eye
   view (coords are floor coords). If uncalibrated, drag on the raw camera frame.
   "Reset both zones".
4. **Stage 3 — Results**: frame slider → camera view (anchor dots orange, zone
   polygons red=occupied/green=empty projected via `inverse()`) + bird's-eye
   view; state caption; timeline area chart; per-machine metrics; transitions
   table.
5. **Copy expander** prints `HOMOGRAPHY_IMAGE_QUAD` + `HOMOGRAPHY_ASPECT` +
   `ZONES` → paste into `config.py`.

### Output contract (for Phase 4 nudge engine)

- `pipeline.snapshot()` → `{zone_id: ZoneStatus}` with `.occupied`, `.machine_id`,
  `.since`, `.person_count`.
- `pipeline.process_frame(frame, ts)` → `list[ZoneStateChange]`
  (`.zone_id`, `.machine_id`, `.occupied`, `.at`, `.to_dict()`).
- `run.py --json-out FILE` mirrors changes to JSONL.
- Config default `STATE_LOG_PATH` env var also available.

### Environment notes

- `cv-service/yolov8n-pose.pt` (~6.5 MB) auto-downloaded — keep it.
- `cv-service/yolov8n.pt` is **dead weight** now (old person-detection model, no
  longer referenced) — safe to delete.
- Core geometry (`homography.project`, `zones`, `smoothing`, `occupancy`,
  `tracker`) is pure Python; `numpy`/`cv2`/`ultralytics` only for the
  playground/runner/`from_quad`/`inverse`.

---

## Run commands

```bash
# booking-service
cd booking-service && python -m pytest -q          # 50 tests
python demo.py

# booking-ui
cd booking-ui && pip install -r requirements.txt && streamlit run app.py

# cv-service
cd cv-service && pip install -r requirements.txt   # yolov8n-pose.pt auto-downloads
python -m pytest -q                                # 53 tests
python demo.py                                     # scripted pose, no weights
streamlit run playground.py                        # calibrate + draw zones + tune
python run.py --source clip.mp4 --show
python run.py --source 0 --json-out ../data/zone_states.jsonl
```

---

## What's next

- **Phase 4 — `integration/nudge_engine.py`**: the only place booking-service +
  cv-service meet. Consume `pipeline.snapshot()` / `ZoneStateChange`s + the
  booking-service `BookingService.bookings(...)` for the active booking per
  machine. Fire **no-show-release** after `config.GRACE_PERIOD` past a booking
  start with the zone still empty; fire **soft-nudge** when a non-reserving
  occupant is present within `config.NUDGE_WINDOW` before a reservation starts.
  Log every event (schedule-adherence % metric). Both services import cleanly;
  the nudge engine needs its own `sys.path` shim for both hyphenated folders (see
  `booking-ui/_bootstrap.py` for the pattern) or run from a script that adds both.
- **Phase 5 — `booking-service/cpsat_scheduler.py`**: `CpSatScheduler` matching
  the `Scheduler` Protocol (`is_available`, `suggest`). `build_scheduler("cpsat")`
  already tries to import it. OR-Tools. Must be a drop-in swap; keep CP-SAT code
  out of `models.py` / cv-service / dashboard.
- **Phase 6 — `dashboard/app.py`**: staff live status of both reserved machines
  (Streamlit), reads the same `data/` store + cv state. Then record the demo.

---

## Memory & plan files

- Persistent memory: `C:\Users\Ahmad\.claude\projects\d--CV-Projects-Book4Workout\memory\`
  — `MEMORY.md` (index) + `phase-progress.md` (has the full phase log).
- cv-service rebuild plan: `C:\Users\Ahmad\.claude\plans\lexical-hopping-stream.md`.
