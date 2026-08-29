"""A failure a user reports has to be findable in the logs.

Before this, a request left one log line with no handle on it: finding the one
a user meant involved guessing from a timestamp, and an unhandled exception
returned "Internal server error" with nothing to quote.

These tests cover the two halves: the id reaches the caller and the log lines,
and a caller-supplied id cannot be used to write a log line of their own.
"""

import logging

import pytest

from api.observability import (
    REQUEST_ID_HEADER,
    log_security_event,
    new_request_id,
    sanitize_request_id,
)
from api.tests.conftest import api_client

# --- the id itself ----------------------------------------------------------


def test_a_fresh_id_is_unique_and_well_formed():
    first, second = new_request_id(), new_request_id()

    assert first != second
    assert sanitize_request_id(first) == first


def test_a_callers_id_is_kept_so_a_trace_survives_the_hop():
    assert sanitize_request_id("client-abc-123") == "client-abc-123"


@pytest.mark.parametrize(
    "hostile",
    [
        "x\nERROR forged line",
        "x\r\n2026-01-01 ERROR nothing happened",
        "x" * 65,
        "id with spaces",
        "id;'/Users/olivier/.claude/scripts/command-validator/bin/safe-rm' -rf /",
        "",
        None,
    ],
)
def test_an_id_that_could_forge_a_log_line_is_replaced(hostile):
    """Not escaped, replaced: there is nothing worth preserving in one."""
    issued = sanitize_request_id(hostile)

    assert issued != hostile
    assert "\n" not in issued and "\r" not in issued
    assert len(issued) <= 64


# --- what the caller gets ---------------------------------------------------


@pytest.mark.asyncio
async def test_every_response_carries_a_request_id():
    async with api_client() as client:
        response = await client.get("/health")

    assert response.headers.get(REQUEST_ID_HEADER)


@pytest.mark.asyncio
async def test_two_requests_get_two_ids():
    async with api_client() as client:
        first = await client.get("/health")
        second = await client.get("/health")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_a_supplied_id_comes_back():
    async with api_client() as client:
        response = await client.get(
            "/health", headers={REQUEST_ID_HEADER: "trace-from-the-gateway"}
        )

    assert response.headers[REQUEST_ID_HEADER] == "trace-from-the-gateway"


@pytest.mark.asyncio
async def test_a_hostile_supplied_id_does_not_come_back():
    async with api_client() as client:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "x" * 200})

    assert response.headers[REQUEST_ID_HEADER] != "x" * 200


# --- what the logs get ------------------------------------------------------


@pytest.mark.asyncio
async def test_the_log_line_for_a_request_carries_its_id(caplog):
    with caplog.at_level(logging.INFO):
        async with api_client() as client:
            response = await client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert any(getattr(record, "request_id", None) == request_id for record in caplog.records), (
        "no log record carried the id the caller was given"
    )


@pytest.mark.asyncio
async def test_a_refused_admin_call_is_logged_as_a_security_event(ordinary_user_and_token, caplog):
    """A refusal nobody records is an attempt nobody can count."""
    _, _, headers = ordinary_user_and_token

    with caplog.at_level(logging.WARNING):
        async with api_client() as client:
            response = await client.get("/admin/trades", headers=headers)

    assert response.status_code == 403
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "security" in messages
    assert "authorization_refused" in messages
    assert "player" in messages


@pytest.mark.asyncio
async def test_a_failed_login_is_logged_as_a_security_event(caplog):
    async with api_client() as client:
        await client.post(
            "/auth/register",
            json={
                "username": "logwatch",
                "email": "logwatch@example.com",
                "name": "Log Watch",
                "password": "LogWatchPassword123",
            },
        )
        with caplog.at_level(logging.WARNING):
            response = await client.post(
                "/auth/login",
                json={"username": "logwatch", "password": "WrongPassword123"},
            )

    assert response.status_code == 401
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "authentication_failed" in messages
    assert "logwatch" in messages


def test_a_security_event_cannot_be_split_across_lines(caplog):
    """Fields come from requests, so one of them will eventually be hostile."""
    logger = logging.getLogger("test.security")

    with caplog.at_level(logging.WARNING):
        log_security_event(
            logger,
            "authentication_failed",
            username="victim\nWARNING security event=nothing_happened",
        )

    assert len(caplog.records) == 1
    assert "\n" not in caplog.records[0].getMessage()


@pytest.mark.asyncio
async def test_hitting_the_login_rate_limit_is_logged(caplog):
    """The signal that distinguishes a forgetful user from a password spray."""
    async with api_client() as client:
        await client.post(
            "/auth/register",
            json={
                "username": "sprayed",
                "email": "sprayed@example.com",
                "name": "Sprayed",
                "password": "SprayedPassword123",
            },
        )
        with caplog.at_level(logging.WARNING):
            for _ in range(7):
                response = await client.post(
                    "/auth/login",
                    json={"username": "sprayed", "password": "WrongPassword123"},
                )

    assert response.status_code == 429
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "rate_limit_reached" in messages
    assert "sprayed" in messages
