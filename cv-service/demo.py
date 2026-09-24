"""Phase 3 smoke demo -- no camera, no model weights.

Feeds a scripted sequence of pose detections through the real anchor + zone +
occupancy stages: nobody -> a person steps onto Reserved Treadmill 1 -> they
leave. Prints the debounced zone-state transitions with timestamps.

Uses the identity homography (floor coords == normalized camera coords), so the
default `config.ZONES` rectangles are hit directly.

    python demo.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from detector import ScriptedPoseDetector, make_pose
from homography import Homography
from pipeline import OccupancyPipeline
from zones import load_zones

FPS = 2.0
STEP = timedelta(seconds=1.0 / FPS)
T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)

# ankle keypoints put the feet anchor at ~(0.30, 0.78) -- inside default zone-1.
ON_TREADMILL_1 = make_pose(
    (0.22, 0.30, 0.40, 0.82),
    {15: (0.28, 0.78, 0.9), 16: (0.32, 0.78, 0.9),          # ankles
     11: (0.29, 0.55, 0.9), 12: (0.31, 0.55, 0.9)},         # hips
)


def main() -> None:
    frames = (
        [[] for _ in range(4)]                    # empty room
        + [[ON_TREADMILL_1] for _ in range(10)]   # someone runs for ~5s
        + [[] for _ in range(10)]                 # they leave
    )

    zones = load_zones()
    pipeline = OccupancyPipeline(
        ScriptedPoseDetector(frames), zones, homography=Homography.identity()
    )

    print(f"zones (floor coords): {[(z.id, z.machine_id, z.rect) for z in zones]}\n")
    for i in range(len(frames)):
        now = T0 + i * STEP
        for change in pipeline.process_frame(None, now):
            state = "OCCUPIED" if change.occupied else "EMPTY   "
            print(f"  {now:%H:%M:%S}  {change.machine_id}  ->  {state}")

    print("\nfinal snapshot:")
    for status in pipeline.snapshot().values():
        print(
            f"  {status.machine_id}: {status.state.value} "
            f"since {status.since:%H:%M:%S} (people={status.person_count})"
        )


if __name__ == "__main__":
    main()
