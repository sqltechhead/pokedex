import pytest

from dex import battery


@pytest.mark.parametrize(
    ("volts", "expected"), [(4.2, 1.0), (4.15, 1.0), (3.725, 0.5), (3.3, 0.0), (3.1, 0.0)]
)
def test_fraction(volts: float, expected: float):
    assert battery.fraction(volts) == pytest.approx(expected)


def test_low():
    assert battery.is_low(3.44)
    assert not battery.is_low(3.45)
