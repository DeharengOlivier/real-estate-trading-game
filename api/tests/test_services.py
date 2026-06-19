"""
Unit tests for pure business-logic helpers in api.services and api.auth.

These exercise the pricing/quarter math and password/JWT helpers directly,
without going through the HTTP layer.
"""
import math
import pytest

from api import services
from api.auth import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
from jose import jwt


# ==================== QUARTER MATH ====================

def test_parse_and_format_quarter():
    assert services.parse_quarter_string("2020-3") == (2020, 3)
    assert services.get_quarter_string(2020, 3) == "2020-3"


@pytest.mark.parametrize("start,n,expected", [
    ("2020-1", 1, "2020-2"),
    ("2020-4", 1, "2021-1"),
    ("2020-1", 4, "2021-1"),
    ("2021-1", -1, "2020-4"),
    ("2020-3", 0, "2020-3"),
])
def test_add_quarters(start, n, expected):
    assert services.add_quarters(start, n) == expected


# ==================== PRICING ====================

def _market_index(zone="Ixelles"):
    return {
        "t": "2020-1",
        "inflation": 0.02, "rate": 0.015, "income": 0.01,
        "unemployment": 0.05, "confidence": 0.0, "policy": 0.0,
        "locals": [{"zone": zone, "access": 0.0, "attract": 0.0,
                    "nuisance": 0.05, "tension": 0.0}],
    }


def test_compute_macro_index_positive():
    assert services.compute_macro_index(_market_index()) > 0


def test_compute_property_price_scales_with_surface():
    prop_small = {"zone": "Ixelles", "type": "apartment", "surface": 50,
                  "epc": 0.5, "state": 0.6, "kitchen": 0.6, "bath": 0.6,
                  "base_ppm": 4000}
    prop_big = dict(prop_small, surface=100)
    mi = _market_index()
    price_small = services.compute_property_price(prop_small, mi)
    price_big = services.compute_property_price(prop_big, mi)
    assert price_big == pytest.approx(2 * price_small)


def test_compute_property_price_unknown_zone_raises():
    prop = {"zone": "Atlantis", "type": "apartment", "surface": 80,
            "epc": 0.5, "state": 0.6, "kitchen": 0.6, "bath": 0.6,
            "base_ppm": 4000}
    with pytest.raises(ValueError):
        services.compute_property_price(prop, _market_index("Ixelles"))


def test_higher_quality_increases_price():
    base = {"zone": "Ixelles", "type": "apartment", "surface": 80,
            "epc": 0.1, "state": 0.1, "kitchen": 0.1, "bath": 0.1,
            "base_ppm": 4000}
    better = dict(base, epc=0.9, state=0.9, kitchen=0.9, bath=0.9)
    mi = _market_index()
    assert services.compute_property_price(better, mi) > \
        services.compute_property_price(base, mi)


# ==================== RENOVATION DELTAS ====================

def test_apply_renovation_delta_clamps_to_unit_interval():
    prop = {"epc": 0.95, "state": 0.5, "kitchen": 0.5, "bath": 0.5, "surface": 100}
    out = services.apply_renovation_delta(
        dict(prop), {"epc": 0.20, "state": 0.0, "kitchen": 0.0, "bath": 0.0}
    )
    assert out["epc"] == 1.0  # clamped at 1


def test_apply_renovation_delta_surface_increase():
    prop = {"epc": 0.5, "state": 0.5, "kitchen": 0.5, "bath": 0.5, "surface": 100}
    out = services.apply_renovation_delta(dict(prop), {"surfacePct": 0.20})
    assert out["surface"] == pytest.approx(120)


# ==================== AUTH HELPERS ====================

def test_password_hash_roundtrip():
    hashed = get_password_hash("TestPassword123")
    assert hashed != "TestPassword123"
    assert verify_password("TestPassword123", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_access_token_encodes_subject():
    token = create_access_token({"sub": "abc123"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "abc123"
    assert "exp" in payload
