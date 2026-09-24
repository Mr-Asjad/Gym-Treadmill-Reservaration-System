"""Reserved Row -- CV Playground (CLAUDE.md Phase 3).

    streamlit run playground.py

Upload a clip from your fixed gym camera, then:
  1. click 4 points that form a rectangle on the floor  -> a bird's-eye view
  2. drag a box over each treadmill on that bird's-eye view
  3. watch the pose -> feet-anchor -> floor-projection -> zone pipeline run and
     tune the debounce / vote window live.

Pose detection runs once and is cached; calibration, zones and debounce re-run
instantly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import config
from analysis import anchors_for, occupied_seconds, replay, run_detection
from homography import QUAD_ORDER, Homography
from zones import Zone

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except Exception as exc:  # pragma: no cover
    st.error("This playground needs `streamlit-image-coordinates` "
             "(`pip install -r requirements.txt`).")
    st.stop()

st.set_page_config(page_title="CV Playground", page_icon="🎥", layout="wide")
st.title("🎥 Reserved Row — CV Playground")
st.caption(
    "Calibrate the floor plane from your one fixed camera, draw the two "
    "treadmill zones on the flattened view, and tune the occupancy pipeline."
)

CAL_W = 620          # calibration image display width (px)
BEV_H = 460          # bird's-eye display height (px)


# --- detection (cached) -----------------------------------------------
@st.cache_resource(show_spinner="Loading YOLO-pose weights…")
def _pose_model():
    from ultralytics import YOLO

    return YOLO(config.POSE_MODEL)


@st.cache_data(show_spinner="Running pose detection over the clip…", max_entries=4)
def detect_run(video_bytes: bytes, name: str, conf: float, every_n: int, max_frames: int):
    from detector import YoloPoseDetector

    suffix = Path(name).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(video_bytes)
        tmp.close()
        detector = YoloPoseDetector(model=_pose_model(), conf_threshold=conf)
        run = run_detection(tmp.name, detector, every_n=every_n, max_frames=max_frames)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    run.source_name = name
    return run


def _decode(jpeg: bytes) -> np.ndarray:
    import cv2

    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    return bgr[:, :, ::-1]                       # -> RGB


def _homography(quad, aspect) -> "Homography | None":
    if len(quad) < 4:
        return Homography.identity()
    try:
        return Homography.from_quad(quad, aspect)
    except Exception:
        return None


def _warp(rgb, hom: Homography, aspect: float):
    """Flatten the camera frame to a top-down (bird's-eye) view."""
    import cv2

    h, w = rgb.shape[:2]
    dw, dh = int(round(BEV_H * aspect)), BEV_H
    s_in = np.array([[1 / w, 0, 0], [0, 1 / h, 0], [0, 0, 1]])
    s_out = np.array([[dw / aspect, 0, 0], [0, dh, 0], [0, 0, 1]])
    m = s_out @ np.array(hom.matrix) @ s_in
    return cv2.warpPerspective(rgb, m, (dw, dh)), dw, dh


def _draw_quad(rgb, quad):
    import cv2

    out = np.ascontiguousarray(rgb).copy()
    h, w = out.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y in quad]
    if len(pts) >= 2:
        cv2.polylines(out, [np.array(pts, np.int32)], len(pts) == 4, (255, 220, 0), 2)
    for i, p in enumerate(pts):
        cv2.circle(out, p, 6, (255, 0, 255), -1)
        cv2.putText(out, str(i + 1), (p[0] + 6, p[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    return out


OCC_RGB, EMPTY_RGB, ANCHOR_RGB = (235, 40, 40), (30, 170, 60), (255, 140, 0)


def _draw_camera(rgb, zones, hom, anchors, timeline, fi):
    import cv2

    out = np.ascontiguousarray(rgb).copy()
    h, w = out.shape[:2]
    inv = hom.inverse() if not hom.is_identity else Homography.identity()
    for a in anchors:
        cx, cy = a["cam"]
        cv2.circle(out, (int(cx * w), int(cy * h)), 6, ANCHOR_RGB, -1)
    for z in zones:
        x1, y1, x2, y2 = z.rect
        poly = np.array(
            [[int(px * w), int(py * h)]
             for px, py in (inv.project(cx, cy)
                            for cx, cy in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])],
            np.int32,
        )
        occ = bool(timeline) and timeline[z.id][fi]
        color = OCC_RGB if occ else EMPTY_RGB
        cv2.polylines(out, [poly], True, color, 3)
        cv2.putText(out, f"{z.machine_id}: {'OCCUPIED' if occ else 'empty'}",
                    (int(poly[:, 0].min()), max(16, int(poly[:, 1].min()) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return out


def _draw_bev(bev, dw, dh, aspect, zones, anchors, timeline, fi):
    import cv2

    out = np.ascontiguousarray(bev).copy()
    for a in anchors:
        fx, fy = a["floor"]
        cv2.circle(out, (int(fx / aspect * dw), int(fy * dh)), 6, ANCHOR_RGB, -1)
    for z in zones:
        x1, y1, x2, y2 = z.rect
        occ = bool(timeline) and timeline[z.id][fi]
        color = OCC_RGB if occ else EMPTY_RGB
        cv2.rectangle(out, (int(x1 / aspect * dw), int(y1 * dh)),
                      (int(x2 / aspect * dw), int(y2 * dh)), color, 3)
        cv2.putText(out, z.machine_id, (int(x1 / aspect * dw), max(16, int(y1 * dh) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return out


def _mk_zone(zid, name, machine_id, rect):
    return Zone(zid, name, machine_id, tuple(round(v, 4) for v in rect))


# --- sidebar --------------------------------------------------------
with st.sidebar:
    st.header("1 · Clip")
    upload = st.file_uploader("Video", type=["mp4", "mov", "avi", "mkv", "webm"])

    st.header("2 · Detection")
    st.caption("Re-runs the pose model.")
    conf = st.slider("Person confidence", 0.0, 1.0, float(config.PERSON_CONF_THRESHOLD), 0.05)
    every_n = st.slider("Sample every Nth frame", 1, 15, 3)
    max_frames = st.slider("Max frames", 30, 600, 240, 30)

    st.header("3 · Occupancy (instant)")
    occ_after = st.slider("Occupied after (s)", 0.0, 3.0, float(config.OCCUPIED_AFTER_SECONDS), 0.1)
    vac_after = st.slider("Vacant after (s)", 0.0, 6.0, float(config.VACANT_AFTER_SECONDS), 0.25)
    vote_window = st.slider("Zone vote window (frames)", 1, 15, int(config.ZONE_VOTE_WINDOW))
    zone_margin = st.slider("Zone margin (floor)", 0.0, 0.15, float(config.ZONE_MARGIN), 0.01)
    kp_conf = st.slider("Ankle keypoint confidence", 0.0, 1.0, float(config.ANKLE_CONF_THRESHOLD), 0.05)
    max_dist = st.slider("Tracker max jump", 0.02, 0.40, float(config.TRACKER_MAX_DISTANCE), 0.02)

if upload is None:
    st.info("⬆️  Upload a short clip (10–40s) from your fixed gym camera to begin.")
    st.stop()

try:
    run = detect_run(upload.getvalue(), upload.name, conf, every_n, max_frames)
except Exception as exc:  # noqa: BLE001
    st.error(f"{type(exc).__name__}: {exc}")
    if "ultralytics" in str(exc):
        st.info("Install the detector deps:  `pip install -r requirements.txt`")
    st.stop()

if run.n_frames == 0 or not run.frames:
    st.error("No frames decoded from that file.")
    st.stop()

with st.sidebar:
    hip_drop = st.slider("Hip-fallback drop (auto)", 0.0, 0.5, float(run.hip_drop), 0.01)

st.session_state.setdefault("quad", [])
st.session_state.setdefault("aspect", float(config.HOMOGRAPHY_ASPECT))
st.session_state.setdefault("zone_target", "z1")
d1, d2 = config.ZONES[0]["rect"], config.ZONES[1]["rect"]
st.session_state.setdefault("z1", tuple(d1))
st.session_state.setdefault("z2", tuple(d2))

# ================= Stage A — calibrate floor plane =================
st.subheader("1 · Calibrate the floor plane")
ca, cb = st.columns([3, 2], gap="large")

with cb:
    st.session_state["aspect"] = st.number_input(
        "Floor rect aspect (width ÷ depth)", 0.2, 5.0, st.session_state["aspect"], 0.1
    )
    ref_i = int(st.number_input("Reference frame", 0, run.n_frames - 1, 0))
    placed = len(st.session_state["quad"])
    st.caption(
        f"Click the **4 corners of a floor rectangle** in order: "
        f"{', '.join(QUAD_ORDER)}  ·  ({placed}/4 placed)"
        + ("" if placed < 4 else "  ✅")
    )
    if st.button("Reset calibration"):
        st.session_state["quad"] = []
        st.rerun()

ref_rgb = _decode(run.frames[ref_i])

with ca:
    got = streamlit_image_coordinates(
        _draw_quad(ref_rgb, st.session_state["quad"]), key="calib", width=CAL_W
    )
    if got and got.get("unix_time") != st.session_state.get("_cal_click"):
        st.session_state["_cal_click"] = got.get("unix_time")
        gw, gh = got.get("width") or CAL_W, got.get("height") or CAL_W
        if len(st.session_state["quad"]) < 4:
            st.session_state["quad"].append(
                [round(got["x"] / gw, 4), round(got["y"] / gh, 4)]
            )
            st.rerun()

hom = _homography(st.session_state["quad"], st.session_state["aspect"])
if hom is None:
    st.error("Those 4 points don't form a usable quad — reset and try again.")
    st.stop()
calibrated = not hom.is_identity

with cb:
    if calibrated:
        bev, dw, dh = _warp(ref_rgb, hom, st.session_state["aspect"])
        st.image(bev, caption="bird's-eye (flattened floor)", width=dw)
    else:
        st.info("Not calibrated yet — zones are drawn on the raw camera frame.")

# ================= Stage B — draw zones ==========================
st.subheader("2 · Draw the two treadmill zones")
aspect = st.session_state["aspect"]
za, zb = st.columns([3, 1], gap="large")

with zb:
    st.session_state["zone_target"] = st.radio(
        "Drawing", ["z1", "z2"],
        format_func=lambda k: "Treadmill 1" if k == "z1" else "Treadmill 2",
        index=0 if st.session_state["zone_target"] == "z1" else 1,
    )
    st.caption("**Drag** a box over that treadmill's deck.")
    if st.button("Reset both zones"):
        st.session_state["z1"], st.session_state["z2"] = tuple(d1), tuple(d2)
        st.rerun()

zones = [
    _mk_zone("zone-1", "Reserved Treadmill 1", "treadmill-1", st.session_state["z1"]),
    _mk_zone("zone-2", "Reserved Treadmill 2", "treadmill-2", st.session_state["z2"]),
]

if calibrated:
    canvas, cdw, cdh = _warp(ref_rgb, hom, aspect)
    canvas = _draw_bev(canvas, cdw, cdh, aspect, zones, [], None, 0)
else:
    canvas = _draw_camera(ref_rgb, zones, hom, [], None, 0)
    ch, cw = canvas.shape[:2]
    cdw, cdh = CAL_W, int(round(CAL_W * ch / cw))

with za:
    drag = streamlit_image_coordinates(canvas, key="zonedraw", width=cdw, click_and_drag=True)
    if drag and drag.get("unix_time") != st.session_state.get("_zone_drag"):
        st.session_state["_zone_drag"] = drag.get("unix_time")
        gw, gh = drag.get("width") or cdw, drag.get("height") or cdh
        xa, xb2 = sorted((drag["x1"] / gw, drag["x2"] / gw))
        ya, yb2 = sorted((drag["y1"] / gh, drag["y2"] / gh))
        if calibrated:
            rect = (xa * aspect, ya, xb2 * aspect, yb2)
        else:
            rect = (xa, ya, xb2, yb2)          # identity: display frac == floor
        if rect[2] - rect[0] > 0.02 and rect[3] - rect[1] > 0.02:
            st.session_state[st.session_state["zone_target"]] = rect
            st.rerun()

# ================= Stage C — results ============================
try:
    result = replay(
        run, zones, hom,
        occupied_after=occ_after, vacant_after=vac_after, max_distance=max_dist,
        zone_margin=zone_margin, min_kp_conf=kp_conf, hip_drop=hip_drop,
        vote_window=vote_window,
    )
except ValueError as exc:
    st.error(f"Zone rectangle invalid: {exc}")
    st.stop()

anchor_rows = anchors_for(run, hom, hip_drop=hip_drop, min_kp_conf=kp_conf)

st.divider()
st.subheader("3 · Occupancy over the clip")
st.caption(
    f"{run.source_name} — {run.n_frames} frames · {run.duration:.1f}s · "
    f"{run.detection_count} people detected · "
    f"{'calibrated' if calibrated else 'uncalibrated (identity)'}"
)

fi = st.slider("Frame", 0, run.n_frames - 1, run.n_frames // 2)
state_now = " · ".join(
    f"{z.machine_id}: {'OCCUPIED' if result.timeline[z.id][fi] else 'empty'}" for z in zones
)
frame_rgb = _decode(run.frames[fi])

vcol1, vcol2 = st.columns(2, gap="medium")
with vcol1:
    st.image(_draw_camera(frame_rgb, zones, hom, anchor_rows[fi], result.timeline, fi),
             use_container_width=True, caption=f"camera · t={run.frame_times[fi]:.2f}s")
with vcol2:
    if calibrated:
        bev, bdw, bdh = _warp(frame_rgb, hom, aspect)
        st.image(_draw_bev(bev, bdw, bdh, aspect, zones, anchor_rows[fi], result.timeline, fi),
                 width=bdw, caption="bird's-eye")
    else:
        st.caption("Calibrate to see the bird's-eye view.")

st.caption(f"**{state_now}**  ·  {len(anchor_rows[fi])} anchor point(s) this frame")

lc, rc = st.columns([3, 2], gap="large")
with lc:
    st.markdown("**Timeline**")
    tl = pd.DataFrame({"seconds": run.frame_times})
    for z in zones:
        tl[z.machine_id] = [int(v) for v in result.timeline[z.id]]
    st.area_chart(tl.set_index("seconds"), height=200)
with rc:
    occ_s = occupied_seconds(run, result)
    for z in zones:
        n = sum(1 for c in result.changes if c.zone_id == z.id)
        st.metric(z.machine_id, f"{occ_s[z.id]:.1f}s used", f"{n} transitions")

st.markdown("**Detected transitions**")
if result.transitions:
    st.dataframe(
        pd.DataFrame([
            {"time": f"{r['t']:.2f}s", "machine": r["machine_id"],
             "state": "OCCUPIED" if r["occupied"] else "empty"}
            for r in result.transitions
        ]),
        hide_index=True, use_container_width=True,
    )
else:
    st.caption("No zone changed state. Check the calibration quad and zone boxes above.")

with st.expander("Copy the calibration + zones into config.py"):
    quad_txt = (
        "[]" if not calibrated
        else "[" + ", ".join(f"[{x:.4f}, {y:.4f}]" for x, y in st.session_state["quad"]) + "]"
    )
    st.code(
        f"HOMOGRAPHY_IMAGE_QUAD = {quad_txt}\n"
        f"HOMOGRAPHY_ASPECT = {aspect:.2f}\n\n"
        "ZONES = [\n"
        + "".join(
            f'    {{"id": "{z.id}", "name": "{z.name}", "machine_id": "{z.machine_id}",\n'
            f'     "rect": ({z.rect[0]:.3f}, {z.rect[1]:.3f}, {z.rect[2]:.3f}, {z.rect[3]:.3f})}},\n'
            for z in zones
        )
        + "]",
        language="python",
    )
