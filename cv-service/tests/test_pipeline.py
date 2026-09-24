from datetime import datetime, timedelta, timezone

from detector import L_ANKLE, L_HIP, R_ANKLE, R_HIP, ScriptedPoseDetector, make_pose
from homography import Homography
from occupancy import ZoneOccupancyMonitor
from pipeline import OccupancyPipeline, assign_zone
from smoothing import ZoneAssignmentSmoother
from zones import Zone, load_zones

T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)

# identity homography => floor coords == normalized camera coords.
# default zones: zone-1 (0.15,0.5,0.45,0.95), zone-2 (0.55,0.5,0.85,0.95)


def feet_at(x, y=0.80, *, conf=0.9):
    return make_pose(
        (x - 0.05, 0.30, x + 0.05, y + 0.05),
        {L_ANKLE: (x, y, conf), R_ANKLE: (x, y, conf)},
    )


def hips_at(x, y=0.55):
    return make_pose(
        (x - 0.12, 0.20, x + 0.12, 0.70),                # deliberately wide bbox
        {L_HIP: (x, y, 0.9), R_HIP: (x, y, 0.9)},        # ankles absent
    )


def run(zones, frames, *, occupied_after=0.0, vacant_after=0.0, zone_margin=0.0,
        vote_window=1, hip_drop=0.10, step=0.1):
    pipe = OccupancyPipeline(
        ScriptedPoseDetector(frames), zones,
        homography=Homography.identity(),
        monitor=ZoneOccupancyMonitor(zones, occupied_after, vacant_after),
        smoother=ZoneAssignmentSmoother(vote_window),
        zone_margin=zone_margin, hip_drop=hip_drop,
    )
    changes = []
    for i in range(len(frames)):
        changes += pipe.process_frame(None, T0 + timedelta(seconds=i * step))
    return pipe, changes


def test_assign_zone_deepest_containment_wins():
    zones = (Zone("a", "A", "m1", (0.0, 0.0, 0.5, 1.0)),
             Zone("b", "B", "m2", (0.45, 0.0, 1.0, 1.0)))
    assert assign_zone(zones, 0.10, 0.5) == "a"
    assert assign_zone(zones, 0.90, 0.5) == "b"
    assert assign_zone(zones, 0.47, 0.5) == "a"      # depth a 0.03 > depth b 0.02
    assert assign_zone(zones, 2.00, 0.5) is None


def test_person_on_treadmill_1_marks_only_that_zone():
    pipe, changes = run(load_zones(), [[feet_at(0.30)]] * 4)
    assert [(c.machine_id, c.occupied) for c in changes] == [("treadmill-1", True)]
    snap = pipe.snapshot()
    assert snap["zone-1"].occupied and not snap["zone-2"].occupied


def test_bent_over_runner_hip_fallback_keeps_the_right_zone():
    # ankles occluded, wide bbox would straddle both zones; hip anchor + drop
    # lands the feet at (0.30, 0.80) -> zone-1 only.
    pipe, changes = run(load_zones(), [[hips_at(0.30)]] * 4, hip_drop=0.25)
    assert [(c.machine_id, c.occupied) for c in changes] == [("treadmill-1", True)]
    assert not pipe.snapshot()["zone-2"].occupied


def test_person_between_machines_occupies_neither():
    _, changes = run(load_zones(), [[feet_at(0.50)]] * 4, zone_margin=0.03)
    assert changes == []


def test_two_people_occupy_both_zones():
    pipe, changes = run(load_zones(), [[feet_at(0.30), feet_at(0.70)]] * 4)
    assert {c.machine_id for c in changes if c.occupied} == {"treadmill-1", "treadmill-2"}


def test_boundary_blip_is_absorbed_by_the_vote_window():
    zones = (Zone("z1", "T1", "treadmill-1", (0.0, 0.0, 0.5, 1.0)),
             Zone("z2", "T2", "treadmill-2", (0.5, 0.0, 1.0, 1.0)))
    # feet sit at 0.44 (zone-1) and blip 0.09 into zone-2 every 3rd frame
    xs = [0.44, 0.44, 0.44] + [0.53 if i % 3 == 0 else 0.44 for i in range(9)]
    frames = [[feet_at(x, 0.5)] for x in xs]

    _, raw = run(zones, frames, vote_window=1)
    _, smoothed = run(zones, frames, vote_window=5)

    assert {c.machine_id for c in raw if c.occupied} == {"treadmill-1", "treadmill-2"}
    assert {c.machine_id for c in smoothed if c.occupied} == {"treadmill-1"}


def test_zone_test_happens_in_floor_space_via_the_homography():
    # homography shifts floor-x by +0.5. A camera anchor at x=0.10 is nowhere
    # near the floor zone, but projects to x=0.60 which is inside it.
    shift = Homography([[1.0, 0.0, 0.5], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    zones = (Zone("z1", "T1", "treadmill-1", (0.5, 0.0, 0.8, 1.0)),)

    def occ(homography):
        pipe = OccupancyPipeline(
            ScriptedPoseDetector([[feet_at(0.10, 0.5)]] * 3), zones,
            homography=homography,
            monitor=ZoneOccupancyMonitor(zones, 0.0, 0.0),
            smoother=ZoneAssignmentSmoother(1), zone_margin=0.0,
        )
        ch = []
        for i in range(3):
            ch += pipe.process_frame(None, T0 + timedelta(seconds=i * 0.1))
        return [(c.machine_id, c.occupied) for c in ch]

    assert occ(shift) == [("treadmill-1", True)]
    assert occ(Homography.identity()) == []


def test_detector_exhaustion_is_harmless():
    pipe, _ = run(load_zones(), [[feet_at(0.30)]] * 2)
    assert isinstance(pipe.process_frame(None, T0 + timedelta(seconds=9)), list)
