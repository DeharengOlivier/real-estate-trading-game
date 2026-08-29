"""Making a single request findable in the logs.

A user reports that something failed. Without a handle, finding the request
means guessing from a timestamp; with one, it is a search. Every request gets
an id, every log line emitted while handling it carries that id, and the
response returns it, so the number in a bug report is the number in the logs.

Two things here are security controls rather than conveniences:

- the id may be supplied by the caller, so it is sanitised before it reaches a
  log line. An unfiltered value could contain newlines and forge log entries.
- authentication failures and authorization refusals are logged deliberately,
  at WARNING, with who and what. An attack that leaves no trace is one nobody
  can answer.
"""

import logging
import re
import uuid
from contextvars import ContextVar

# The id of the request being handled, per task. Empty outside a request, which
# is what startup and shutdown lines get.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Header the id is read from and returned in.
REQUEST_ID_HEADER = "X-Request-ID"

# What a caller-supplied id may contain. Deliberately narrow: this value is
# written into log lines, and a newline in a log line is a forged log line.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


def new_request_id() -> str:
    """A fresh id for a request that did not bring one."""
    return uuid.uuid4().hex


def sanitize_request_id(supplied: str | None) -> str:
    """Accept a caller's request id, or issue one.

    A caller passing its own id is how a trace survives across services. A
    caller passing ``"x\\nERROR fake line"`` is how a log file starts lying, so
    anything outside :data:`SAFE_REQUEST_ID` is replaced rather than escaped:
    there is nothing to preserve in a malformed id.

    Args:
        supplied: The incoming header value, or None.

    Returns:
        The supplied id when it is well formed, otherwise a fresh one.
    """
    if supplied and SAFE_REQUEST_ID.match(supplied):
        return supplied
    return new_request_id()


def bind_request_id(request_id: str):
    """Make ``request_id`` the one every log line in this task reports."""
    return _request_id.set(request_id)


def reset_request_id(token) -> None:
    """Undo one :func:`bind_request_id`, so tasks do not leak into each other."""
    _request_id.reset(token)


def current_request_id() -> str:
    """The id of the request being handled, or "-" outside one."""
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Put the current request id on every record, so the format can use it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Send logs to stderr in a format that carries the request id.

    Called once, at import of the application. Existing handlers are given the
    filter too, so uvicorn's own lines are formatted the same way.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_security_event(logger: logging.Logger, event: str, **fields) -> None:
    """Record something an incident review would want to find.

    Refusals are the interesting ones: a single 403 is a misconfigured client,
    a hundred is somebody trying doors. They are logged at WARNING so they
    stand out from ordinary traffic, as ``key=value`` pairs so they can be
    counted without parsing prose.

    Values are stringified and stripped of anything that could break a line,
    since some of them come from a request.
    """
    details = " ".join(f"{key}={_flatten(value)}" for key, value in sorted(fields.items()))
    logger.warning("security event=%s %s", event, details)


def _flatten(value: object) -> str:
    """One line, no separators: safe to drop into a key=value log line."""
    text = str(value)
    for character in ("\n", "\r", "\t", " "):
        text = text.replace(character, "_")
    return text or "-"
