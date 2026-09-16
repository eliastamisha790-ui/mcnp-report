import pytest

from mcnp_report.numbers import parse_mcnp_number, strip_asa


@pytest.mark.parametrize("text, expected", [
    ("1.58-01", 0.158), ("5.01-05", 5.01e-5), ("1.00+00", 1.0),
    ("4.95542E-04", 4.95542e-4), ("0.", 0.0),
])
def test_mcnp_number(text, expected):
    assert parse_mcnp_number(text) == pytest.approx(expected)


def test_asa_control_character():
    assert strip_asa("1tally        4") == ("1", "tally        4")
    assert strip_asa(" normal line") == (" ", "normal line")

