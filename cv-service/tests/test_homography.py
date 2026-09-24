import pytest

from homography import Homography

QUAD = [(0.20, 0.30), (0.80, 0.30), (0.95, 0.90), (0.05, 0.90)]  # TL, TR, BR, BL


def test_identity_passes_points_through():
    h = Homography.identity()
    assert h.project(0.3, 0.7) == (0.3, 0.7)
    assert h.is_identity


def test_project_is_plain_matrix_math():
    h = Homography([[2.0, 0.0, 0.1], [0.0, 3.0, -0.2], [0.0, 0.0, 1.0]])
    assert h.project(0.5, 0.5) == pytest.approx((1.1, 1.3))


def test_from_quad_maps_the_quad_onto_the_unit_rectangle():
    h = Homography.from_quad(QUAD, aspect=1.0)
    got = [h.project(*p) for p in QUAD]
    for g, e in zip(got, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        assert g == pytest.approx(e, abs=1e-9)


def test_point_inside_the_quad_lands_inside_the_unit_rect():
    h = Homography.from_quad(QUAD)
    fx, fy = h.project(0.5, 0.6)
    assert 0.0 < fx < 1.0 and 0.0 < fy < 1.0


def test_inverse_round_trips():
    h = Homography.from_quad(QUAD)
    inv = h.inverse()
    fx, fy = h.project(0.42, 0.55)
    assert inv.project(fx, fy) == pytest.approx((0.42, 0.55), abs=1e-9)


def test_aspect_stretches_the_x_axis():
    axis_aligned = [(0.2, 0.3), (0.8, 0.3), (0.8, 0.9), (0.2, 0.9)]
    h = Homography.from_quad(axis_aligned, aspect=2.0)
    assert h.project(0.8, 0.3) == pytest.approx((2.0, 0.0), abs=1e-9)
    assert h.project(0.5, 0.6) == pytest.approx((1.0, 0.5), abs=1e-9)


def test_from_quad_rejects_wrong_point_count():
    with pytest.raises(ValueError):
        Homography.from_quad([(0, 0), (1, 0), (1, 1)])


def test_serialize_round_trip():
    h = Homography.from_quad(QUAD, aspect=1.3)
    back = Homography.from_dict(h.to_dict())
    assert back.matrix == h.matrix
    assert back.aspect == 1.3
