"""Who may call this API from a browser is a deployment decision.

The allowed origins were two localhost URLs written into main.py, so the
shipped image could not serve any real frontend and there was no way to tell it
about one without editing the source. They come from the environment now, and
the parsing is what these tests pin: a deployment that gets this wrong either
cannot be used or lets any site call the API with the user's credentials.
"""

import pytest

from api.cors import DEFAULT_ALLOWED_ORIGINS, allowed_origins_from_env
from api.tests.conftest import api_client


def test_the_default_is_the_local_development_frontend():
    assert allowed_origins_from_env(None) == list(DEFAULT_ALLOWED_ORIGINS)
    assert allowed_origins_from_env("") == list(DEFAULT_ALLOWED_ORIGINS)
    assert allowed_origins_from_env("   ") == list(DEFAULT_ALLOWED_ORIGINS)


def test_one_origin():
    assert allowed_origins_from_env("https://game.example.com") == ["https://game.example.com"]


def test_several_origins_with_whatever_spacing():
    assert allowed_origins_from_env(" https://game.example.com , https://staging.example.com ") == [
        "https://game.example.com",
        "https://staging.example.com",
    ]


def test_a_trailing_slash_is_dropped():
    """An Origin header never carries a path, so a trailing slash never matches."""
    assert allowed_origins_from_env("https://game.example.com/") == ["https://game.example.com"]


def test_duplicates_collapse_but_order_is_kept():
    assert allowed_origins_from_env("https://a.example.com,https://a.example.com") == [
        "https://a.example.com"
    ]


@pytest.mark.parametrize("wildcard", ["*", "https://a.example.com,*", " * "])
def test_a_wildcard_is_refused(wildcard):
    """The API answers with credentials, so `*` is not a configuration.

    A browser will not send credentials to a wildcard origin, so allowing one
    here does not widen access, it silently breaks every authenticated request.
    Refusing at startup says so, instead of leaving somebody to discover it
    from a support ticket.
    """
    with pytest.raises(ValueError, match=r"\*"):
        allowed_origins_from_env(wildcard)


@pytest.mark.parametrize(
    "malformed",
    [
        "game.example.com",  # no scheme
        "https://game.example.com/play",  # a path
        "ftp://game.example.com",  # not a browser origin
        "http://",  # no host
    ],
)
def test_something_that_is_not_an_origin_is_refused(malformed):
    """A value that can never match is a typo, and typos fail at startup."""
    with pytest.raises(ValueError):
        allowed_origins_from_env(malformed)


def test_the_message_names_the_variable():
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        allowed_origins_from_env("nonsense")


# --- the middleware, not just the parser ------------------------------------
#
# The list is read once, when the app is built, so these exercise the default
# rather than an override: what matters here is that the parsed list actually
# reaches the middleware and that an origin outside it gets nothing back.


@pytest.mark.asyncio
async def test_the_configured_origin_is_allowed_through():
    async with api_client() as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_an_origin_outside_the_list_gets_no_permission():
    async with api_client() as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") is None


@pytest.mark.asyncio
async def test_a_request_from_an_unlisted_origin_carries_no_permission_header():
    """A plain request is answered; what it must not carry is the permission
    that would let the calling page read the answer."""
    async with api_client() as client:
        response = await client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None
