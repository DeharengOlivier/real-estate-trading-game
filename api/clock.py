"""One way to say "now", and one way to read a stored timestamp.

``datetime.utcnow()`` returns a naive datetime that claims to be UTC: nothing
on the object says which zone it is in, so any comparison with an aware one
raises, and any comparison with a *differently* naive one is silently wrong.
Python has deprecated it and scheduled it for removal.

Everything in this project stamps with :func:`utc_now` instead. Reading back is
the other half of the problem: pymongo returns naive datetimes by default,
while a document built in memory (a test, a fixture) holds whatever it was
given. :func:`as_utc` makes both comparable without caring which one it got.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """The current moment, carrying the zone it is in."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Read a stored timestamp as UTC, whether or not it says so.

    A naive value is assumed to be UTC, which is what it is: every timestamp
    this project writes is UTC, and pymongo strips the zone on the way out.

    Args:
        value: A datetime from a document, aware or naive.

    Returns:
        The same moment, with tzinfo set.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
