"""Timestamps carry the zone they are in.

Every datetime this project writes is UTC, and used to be written with
``datetime.utcnow()``, which returns a value that is UTC and does not say so.
Nothing goes wrong until something compares it: an aware value and a naive one
raise TypeError, and two naive ones from different sources compare silently and
wrongly.
"""

from datetime import UTC, datetime, timedelta

import pytest

from api.clock import as_utc, utc_now


def test_now_carries_its_zone():
    assert utc_now().tzinfo is not None
    assert utc_now().utcoffset() == timedelta(0)


def test_now_is_now():
    """A stamp that is not the current moment is a different bug entirely."""
    before = datetime.now(UTC)
    stamped = utc_now()
    after = datetime.now(UTC)

    assert before <= stamped <= after


def test_a_naive_value_is_read_as_utc():
    """pymongo strips the zone on the way out; this puts it back."""
    naive = datetime(2026, 3, 14, 15, 9, 26)

    restored = as_utc(naive)

    assert restored.tzinfo is UTC
    assert restored.replace(tzinfo=None) == naive


def test_an_aware_value_is_left_alone():
    """A document built in memory keeps whatever zone it was given."""
    aware = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)

    assert as_utc(aware) is aware


def test_a_naive_and_an_aware_value_of_the_same_moment_compare_equal():
    """The point of the helper: two sources, one comparison."""
    moment = datetime(2026, 3, 14, 15, 9, 26)

    from_the_driver = as_utc(moment)
    from_a_fixture = as_utc(moment.replace(tzinfo=UTC))

    assert from_the_driver == from_a_fixture


def test_comparing_without_the_helper_is_the_error_it_prevents():
    """Names why the helper exists, so removing it fails loudly."""
    naive = datetime(2026, 3, 14, 15, 9, 26)
    aware = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)

    with pytest.raises(TypeError):
        _ = naive < aware
