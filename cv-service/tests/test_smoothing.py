from smoothing import ZoneAssignmentSmoother


def feed(smoother, track_id, sequence):
    out = None
    for zone in sequence:
        out = smoother.update({track_id: zone})[track_id]
    return out


def test_minority_flicker_is_held_to_the_majority():
    s = ZoneAssignmentSmoother(window=5)
    # 3x zone-1, 2x zone-2 in the window -> zone-1
    assert feed(s, 0, ["zone-1", "zone-1", "zone-2", "zone-1", "zone-2"]) == "zone-1"


def test_sustained_switch_flips_once_it_is_the_majority():
    s = ZoneAssignmentSmoother(window=3)
    feed(s, 0, ["zone-1", "zone-1", "zone-1"])
    assert s.update({0: "zone-2"})[0] == "zone-1"   # z1:2 z2:1
    assert s.update({0: "zone-2"})[0] == "zone-2"   # z1:1 z2:2


def test_a_tie_reports_no_zone():
    s = ZoneAssignmentSmoother(window=2)
    assert s.update({0: "zone-1"})[0] == "zone-1"
    assert s.update({0: "zone-2"})[0] is None       # 1-1 tie


def test_none_is_a_valid_assignment():
    s = ZoneAssignmentSmoother(window=3)
    for _ in range(3):
        assert s.update({0: None})[0] is None


def test_tracks_are_independent():
    s = ZoneAssignmentSmoother(window=3)
    s.update({0: "zone-1", 1: "zone-2"})
    assert s.update({0: "zone-1", 1: "zone-2"}) == {0: "zone-1", 1: "zone-2"}


def test_stale_tracks_are_pruned():
    s = ZoneAssignmentSmoother(window=2)
    s.update({7: "zone-1"})
    for _ in range(3):
        s.update({})
    assert 7 not in s._hist
