"""CLI runner for the CV occupancy service (CLAUDE.md Phase 3).

    python run.py --source 0            # webcam
    python run.py --source clip.mp4 --show
    python run.py --source 0 --json-out ../data/zone_states.jsonl

Prints a line every time a reserved-treadmill zone flips empty <-> occupied.
Needs `ultralytics` + `opencv-python` (see requirements.txt). Zones and the
homography come from config -- calibrate them in the playground first.
"""
from __future__ import annotations

import argparse
import json
import sys

import config
from detector import YoloPoseDetector
from feed import VideoFeed
from homography import load_homography
from pipeline import OccupancyPipeline
from zones import load_zones


def _draw(cv2, np, frame, zones, homography, snapshot):
    h, w = frame.shape[:2]
    inv = homography.inverse()
    for z in zones:
        x1, y1, x2, y2 = z.rect
        corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        pts = []
        for fx, fy in corners:
            cx, cy = inv.project(fx, fy)
            pts.append([int(cx * w), int(cy * h)])
        st = snapshot[z.id]
        color = (0, 0, 255) if st.occupied else (0, 200, 0)
        cv2.polylines(frame, [np.array(pts, np.int32)], True, color, 2)
        cv2.putText(frame, f"{z.machine_id}: {st.state.value} ({st.person_count})",
                    (pts[0][0], max(16, pts[0][1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reserved-treadmill occupancy detector")
    ap.add_argument("--source", default=config.VIDEO_SOURCE)
    ap.add_argument("--show", action="store_true", help="annotated preview window")
    ap.add_argument("--json-out", help="append zone state changes as JSONL")
    args = ap.parse_args(argv)

    zones = load_zones()
    homography = load_homography()
    pipeline = OccupancyPipeline(YoloPoseDetector(), zones, homography=homography)
    feed = VideoFeed(args.source)
    sink = open(args.json_out, "a", encoding="utf-8") if args.json_out else None
    cv2 = np = None
    if args.show:
        import cv2  # noqa: F811
        import numpy as np  # noqa: F811

    print(f"watching {[z.machine_id for z in zones]} (source={args.source}"
          f"{', uncalibrated' if homography.is_identity else ''}) ...")
    try:
        for timestamp, frame in feed:
            for change in pipeline.process_frame(frame, timestamp):
                line = json.dumps(change.to_dict())
                print(line, flush=True)
                if sink:
                    sink.write(line + "\n")
                    sink.flush()
            if args.show:
                cv2.imshow(
                    "Reserved Row - occupancy",
                    _draw(cv2, np, frame, zones, homography, pipeline.snapshot()),
                )
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        feed.release()
        if sink:
            sink.close()
        if args.show and cv2 is not None:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
