"""Which browser origins may call this API.

Hard-coding them made the shipped image unusable by any real frontend, so they
come from CORS_ALLOWED_ORIGINS, comma separated. The parsing lives here rather
than inline in main.py because it is the one place a deployment can lock itself
out of its own API, and it is worth testing.

The rule is: fail at startup on anything that cannot work, rather than start
and let it be discovered from a support ticket.
"""

from urllib.parse import urlsplit

# Where the frontend runs under `docker compose up`, which is the only origin a
# checkout needs before it is deployed anywhere.
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

ENV_VAR = "CORS_ALLOWED_ORIGINS"

# An Origin header is a scheme, a host and an optional port. Nothing else.
BROWSER_SCHEMES = ("http", "https")


def _validate(origin: str) -> str:
    """Check one origin, or raise saying what is wrong with it."""
    if origin == "*":
        raise ValueError(
            f"{ENV_VAR} contains '*'. This API answers with credentials, and a "
            "browser will not send credentials to a wildcard origin: allowing "
            "one does not widen access, it breaks every authenticated request. "
            "List the origins instead."
        )

    parts = urlsplit(origin)
    if parts.scheme not in BROWSER_SCHEMES:
        raise ValueError(
            f"{ENV_VAR} entry {origin!r} has no http:// or https:// scheme. "
            "An Origin header always carries one, so this can never match."
        )
    if not parts.netloc:
        raise ValueError(f"{ENV_VAR} entry {origin!r} has no host.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(
            f"{ENV_VAR} entry {origin!r} carries a path. An Origin header is a "
            "scheme, a host and a port, and nothing else."
        )

    return f"{parts.scheme}://{parts.netloc}"


def allowed_origins_from_env(raw: str | None) -> list[str]:
    """Parse CORS_ALLOWED_ORIGINS, or fall back to the development frontend.

    Args:
        raw: The environment variable's value, or None when it is unset.

    Returns:
        The origins to allow, in the order given, without duplicates.

    Raises:
        ValueError: An entry is a wildcard, or is not a browser origin. The
            message names the variable and the offending entry.
    """
    if raw is None or not raw.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)

    origins = [_validate(entry.strip()) for entry in raw.split(",") if entry.strip()]

    # dict preserves insertion order, so this drops repeats without shuffling.
    return list(dict.fromkeys(origins))
