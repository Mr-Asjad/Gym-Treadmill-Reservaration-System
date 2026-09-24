# cv-service

Webcam occupancy detection for the two reserved treadmills (CLAUDE.md Phase 3).
**Zero dependency on the booking service** — they only meet in
`integration/nudge_engine.py` (Phase 4).

Occupancy detection only: "is a person present in zone X". No facial
recognition, no re-ID, no identity database (CLAUDE.md "Core Product Decisions").

## Approach (CLAUDE.md "Zone Detection Approach")

```
frame
 → YOLOv8-pose ........... person bbox + 17 COCO keypoints
 → anchor_point() ........ feet = ankle midpoint (kp 15/16); if the ankles are
                           occluded (side angle, console), hip midpoint (11/12)
                           shifted down by an auto-derived offset; else skip
 → CentroidTracker ....... track the anchor point across frames (ephemeral ids)
 → Homography.project() .. anchor (camera) → flattened top-down FLOOR coords
 → assign_zone() ......... point-in-rectangle in floor space; deepest-containment
                           wins so one person is never on two machines
 → ZoneAssignmentSmoother  majority vote of each track's zone over N frames
 → ZoneOccupancyMonitor .. debounced empty/occupied + timestamped changes
```

Why: raw bbox / bbox-overlap against camera-pixel boxes breaks at a side angle —
a bent-over runner's wide bbox spills into the next lane. Comparing **feet
positions in a flattened floor plane** removes the camera-angle distortion.

## Files

| File | Role |
|---|---|
| `config.py` | pose model, keypoint/zone thresholds, homography quad, floor zones, debounce, vote window — all env-overridable |
| `homography.py` | `Homography` — `project()` (pure), `from_quad()` (4 floor points → canonical top-down rect), `inverse()`, `load_homography()` |
| `detector.py` | `Keypoint`/`PoseDetection`, `PoseDetector` protocol, `YoloPoseDetector`, `ScriptedPoseDetector`, `anchor_point()` |
| `tracker.py` | `CentroidTracker` — unchanged |
| `smoothing.py` | `ZoneAssignmentSmoother` — rolling majority vote on a track's zone |
| `zones.py` | `Zone` — **floor-coordinate** rectangle; `contains()`, `depth()` |
| `occupancy.py` | `ZoneOccupancyMonitor` — debounce state machine — unchanged |
| `pipeline.py` | `OccupancyPipeline` + `assign_zone()` |
| `analysis.py` | `run_detection()` (detect once), `replay()` (re-tune instantly), `anchors_for()`, `derive_hip_drop()` |
| `playground.py` | Streamlit: calibrate the floor plane, draw zones on the bird's-eye view, tune live |
| `feed.py` / `run.py` | OpenCV frame source + CLI runner |

## Run

```bash
pip install -r requirements.txt        # yolov8n-pose.pt auto-downloads (~6.5 MB)

python demo.py                          # scripted pose, no camera / no weights
streamlit run playground.py             # calibrate + draw zones + tune
python run.py --source clip.mp4 --show  # live, zone polygons drawn back on camera
pytest                                  # 53 tests
```

## Calibrating (playground)

**No overhead camera.** The bird's-eye view is synthesised from your one fixed
side-angle camera.

1. Upload a clip. Pose detection runs once (cached).
2. **Click 4 points** that form a rectangle on the real floor (mat corners,
   floor tape, tile seams), in order: top-left, top-right, bottom-right,
   bottom-left. A flattened top-down view appears.
3. **Drag a box** over each treadmill's deck on that top-down view.
4. Check the timeline / transitions, then paste the printed
   `HOMOGRAPHY_IMAGE_QUAD` + `HOMOGRAPHY_ASPECT` + `ZONES` block into `config.py`.

Uncalibrated (`HOMOGRAPHY_IMAGE_QUAD = []`) falls back to identity — floor coords
== camera coords — so tests and a roughly-overhead camera still work, without
perspective correction.

## Output contract (for Phase 4)

- `pipeline.snapshot()` → `{zone_id: ZoneStatus}` (`.occupied`, `.machine_id`,
  `.since`, `.person_count`).
- `pipeline.process_frame(frame, ts)` → list of `ZoneStateChange`
  (`zone_id`, `machine_id`, `occupied`, `at`). `run.py --json-out` mirrors these.

## Tuning knobs (`config.py`, playground sliders)

- `OCCUPIED_AFTER_SECONDS` (0.3) / `VACANT_AFTER_SECONDS` (1.5) — debounce; a
  missed pose frame mid-run does not restart the occupied clock.
- `ZONE_VOTE_WINDOW` (5) — frames of majority vote before a track's zone flips;
  absorbs someone reaching between machines.
- `ZONE_MARGIN` (0.03) — floor-space slack on the zone rectangle.
- `ANKLE_CONF_THRESHOLD` (0.30) — below this, the hip-fallback anchor is used.
