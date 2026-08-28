"""Parsing object ids that arrive in a URL path.

Ids in a request *body* are parsed by pydantic through
:data:`api.models.ObjectIdStr`, which answers 422 with the offending field
named. Path segments are parsed here instead, because these endpoints already
answer 400 for a malformed id and that contract is what clients are written
against.

Either way the rule is the same: parse once, at the boundary, and let every
handler past it construct an ObjectId without a guard.
"""
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status


def parse_object_id(value: str, what: str = "ID") -> ObjectId:
    """Parse a path segment into an ObjectId, or answer 400.

    Args:
        value: The raw path segment.
        what: How to name the identifier in the error message, e.g. "property ID".

    Returns:
        The parsed ObjectId.

    Raises:
        HTTPException: 400, when ``value`` is not a valid object id.

    The except clause names ``InvalidId`` on purpose. A bare ``except`` here
    would also swallow a KeyboardInterrupt, and would report any unrelated
    programming error inside the block as a malformed identifier.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {what}",
        )
