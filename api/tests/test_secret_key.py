"""The JWT signing key is a credential, so a missing one fails closed.

These tests run the import in a subprocess with a controlled environment,
because the check happens at import time: that is the earliest point at which
the process can refuse, and it cannot be reached around. A test inside this
process could only observe the key that was already accepted when the suite
started.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 256 bits of key material, the minimum for HS256, expressed as hex.
A_GOOD_KEY = "a" * 64


def _import_api_auth_with(secret_key):
    """Import api.auth in a fresh process, with SECRET_KEY set or removed."""
    env = dict(os.environ)
    if secret_key is None:
        env.pop("SECRET_KEY", None)
    else:
        env["SECRET_KEY"] = secret_key

    return subprocess.run(
        [sys.executable, "-c", "import api.auth"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_missing_secret_key_refuses_to_start():
    result = _import_api_auth_with(None)

    assert result.returncode != 0, "the API started with no signing key"
    assert "SECRET_KEY" in result.stderr


def test_the_refusal_says_how_to_produce_a_key():
    """An error that only says "missing" costs the reader a search."""
    result = _import_api_auth_with(None)

    assert "openssl rand" in result.stderr or "secrets.token" in result.stderr


@pytest.mark.parametrize(
    "placeholder",
    [
        "change-me-please",
        "change-me-in-production",
        "please-set-secret-key-in-env-file",
    ],
)
def test_a_placeholder_key_is_refused(placeholder):
    """These three strings shipped in this repository. They are public."""
    result = _import_api_auth_with(placeholder)

    assert result.returncode != 0, f"{placeholder!r} was accepted as a key"
    assert "SECRET_KEY" in result.stderr


@pytest.mark.parametrize("weak", ["", "   ", "short", "a" * 31])
def test_a_key_with_too_little_material_is_refused(weak):
    """HS256 signs with the key itself: under 256 bits it is brute-forceable."""
    result = _import_api_auth_with(weak)

    assert result.returncode != 0, f"{weak!r} was accepted as a key"


def test_a_real_key_is_accepted():
    """The gate must refuse the placeholder without refusing a real key."""
    result = _import_api_auth_with(A_GOOD_KEY)

    assert result.returncode == 0, result.stderr
