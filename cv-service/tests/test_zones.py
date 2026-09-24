import pytest

from zones import Zone, load_zones


def test_zone_rejects_a_degenerate_rectangle():
    with pytest.raises(ValueError):
        Zone("z", "Z", "m", (0.5, 0.1, 0.5, 0.9))     # zero width
    with pytest.raises(ValueError):
        Zone("z", "Z", "m", (0.5, 0.9, 0.7, 0.1))     # y flipped


def test_floor_coords_may_exceed_the_unit_range():
    # floor space is not pixel space
    z = Zone("z", "Z", "m", (0.5, 0.2, 1.8, 1.1))
    assert z.contains(1.2, 0.9)


def test_contains_with_margin():
    z = Zone("z", "Z", "m", (0.2, 0.2, 0.8, 0.8))
    assert z.contains(0.5, 0.5)
    assert not z.contains(0.85, 0.5)
    assert z.contains(0.85, 0.5, margin=0.06)
    assert not z.contains(0.85, 0.5, margin=0.02)


def test_depth_is_positive_inside_negative_outside():
    z = Zone("z", "Z", "m", (0.0, 0.0, 1.0, 1.0))
    assert z.depth(0.5, 0.5) == pytest.approx(0.5)
    assert z.depth(0.1, 0.5) == pytest.approx(0.1)
    assert z.depth(-0.2, 0.5) == pytest.approx(-0.2)


def test_default_zones_map_to_the_two_reserved_machines():
    zones = load_zones()
    assert [z.machine_id for z in zones] == ["treadmill-1", "treadmill-2"]
    a, b = sorted(zones, key=lambda z: z.rect[0])
    assert a.rect[2] <= b.rect[0]        # disjoint on the floor
