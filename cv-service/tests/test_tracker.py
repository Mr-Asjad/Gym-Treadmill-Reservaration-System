from tracker import CentroidTracker


def box_at(cx, cy, s=0.05):
    return (cx - s, cy - s, cx + s, cy + s)


def test_empty_frame_returns_nothing():
    t = CentroidTracker()
    assert t.update([]) == {}


def test_single_object_keeps_its_id_while_moving_slowly():
    t = CentroidTracker(max_distance=0.1, max_disappeared=3)
    ids = []
    for cx in (0.20, 0.24, 0.28, 0.32):
        out = t.update([box_at(cx, 0.5)])
        assert len(out) == 1
        ids.append(next(iter(out)))
    assert len(set(ids)) == 1


def test_two_objects_get_distinct_stable_ids():
    t = CentroidTracker(max_distance=0.1, max_disappeared=3)
    out1 = t.update([box_at(0.2, 0.5), box_at(0.8, 0.5)])
    out2 = t.update([box_at(0.22, 0.5), box_at(0.78, 0.5)])
    assert set(out1) == set(out2)
    assert len(out1) == 2


def test_big_jump_is_treated_as_a_new_object():
    t = CentroidTracker(max_distance=0.1, max_disappeared=5)
    (first_id,) = t.update([box_at(0.2, 0.5)])
    out = t.update([box_at(0.9, 0.5)])
    assert first_id not in out
    assert len(out) == 1


def test_object_dropped_after_max_disappeared_then_reregistered():
    t = CentroidTracker(max_distance=0.1, max_disappeared=2)
    (first_id,) = t.update([box_at(0.5, 0.5)])
    for _ in range(3):        # gone for longer than max_disappeared
        t.update([])
    out = t.update([box_at(0.5, 0.5)])
    assert first_id not in out


def test_brief_dropout_keeps_the_id():
    t = CentroidTracker(max_distance=0.1, max_disappeared=3)
    (first_id,) = t.update([box_at(0.5, 0.5)])
    t.update([])             # 1 frame missing (within tolerance)
    out = t.update([box_at(0.51, 0.5)])
    assert list(out) == [first_id]
