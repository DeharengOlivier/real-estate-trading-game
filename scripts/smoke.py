"""Exercise the guards against a running stack, not the in-memory double.

The test suite runs on mongomock, which is fast and needs no services, but it
is not MongoDB. The conditional writes that decide who gets a property and
whose balance is debited depend on the database applying a filter and an update
as one operation; a double that got that wrong would keep the suite green.

So this runs the same invariants against the compose stack: real MongoDB, real
Redis, real HTTP, the images as they are built. It is a smoke test, not a
replacement for the suite: a handful of end-to-end checks that would each be a
serious defect if they failed.

Usage:
    python -m scripts.smoke [base-url]
"""

import asyncio
import sys
import time

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
PASSWORD = "SmokeTestPassword123"

# The account the seed creates and prints. Not a credential worth protecting:
# the seeded database is dropped and rebuilt on every run.
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"


class SmokeFailure(AssertionError):
    """A check that would be a serious defect in production."""


def check(condition, message):
    if not condition:
        raise SmokeFailure(message)


async def register(client, base_url, username):
    response = await client.post(
        f"{base_url}/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "name": username,
            "password": PASSWORD,
        },
    )
    if response.status_code == 429:
        # Registration is limited per calling address, so several runs in a row
        # against one stack use the hour's budget up. That is the limiter
        # working, not a broken guard, and it should not read like one.
        raise SmokeFailure(
            "registration is rate limited for this address, which is the limiter doing "
            "its job after several runs. Start from a clean stack "
            "(docker compose down -v && docker compose up -d) or wait out the window."
        )
    check(response.status_code == 201, f"register {username}: {response.text}")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def run(base_url):
    # Usernames are unique in the database, and this may run twice against the
    # same stack, so they carry the start time.
    stamp = str(int(time.time()))

    async with httpx.AsyncClient(timeout=30) as client:
        health = await client.get(f"{base_url}/health")
        check(health.status_code == 200, f"/health: {health.text}")
        print(f"health                          {health.json()['status']}")

        login = await client.post(
            f"{base_url}/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
        )
        check(login.status_code == 200, f"seeded account cannot log in: {login.text}")
        admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        print("seeded account logs in         yes")

        player = await register(client, base_url, f"smoke_a_{stamp}")
        rival = await register(client, base_url, f"smoke_b_{stamp}")

        refused = await client.get(f"{base_url}/admin/trades", headers=player)
        check(refused.status_code == 403, f"a player read every trade: {refused.text}")
        allowed = await client.get(f"{base_url}/admin/trades", headers=admin_headers)
        check(allowed.status_code == 200, f"an admin was refused: {allowed.text}")
        print("admin surface                  403 for a player, 200 for an admin")

        clock = await client.post(f"{base_url}/game/advance-quarter", headers=player)
        check(clock.status_code == 403, f"a player moved the clock: {clock.text}")
        print("game clock                     403 for a player")

        listings = await client.get(f"{base_url}/trading/listings?limit=1")
        check(listings.status_code == 200, f"/trading/listings: {listings.text}")
        items = listings.json()["items"]
        check(bool(items), "no property is on the market: is the seed loaded?")
        property_id = items[0]["propertyId"]

        # The invariant the conditional writes exist for, against a real
        # MongoDB running as a standalone, where transactions are unavailable.
        first, second = await asyncio.gather(
            client.post(
                f"{base_url}/trading/buy", headers=player, json={"propertyId": property_id}
            ),
            client.post(f"{base_url}/trading/buy", headers=rival, json={"propertyId": property_id}),
        )
        outcome = sorted([first.status_code, second.status_code])
        check(
            outcome == [200, 404],
            f"two buyers for one property answered {outcome}: {first.text} / {second.text}",
        )
        print("one property, two buyers       200 and 404")

        for name, headers in (("buyer", player), ("rival", rival)):
            summary = await client.get(f"{base_url}/portfolio/summary", headers=headers)
            me = await client.get(f"{base_url}/auth/me", headers=headers)
            cash = summary.json()["cash"]
            check(cash >= 0, f"{name} has a negative balance: {cash}")
            check(
                abs(cash - me.json()["cashBalance"]) < 0.01,
                f"{name}: /auth/me says {me.json()['cashBalance']}, portfolio says {cash}",
            )
        print("balances                       non-negative and reported once")

        duplicate = await client.post(
            f"{base_url}/auth/register",
            json={
                "username": f"smoke_a_{stamp}",
                "email": "someone.else@example.com",
                "name": "duplicate",
                "password": PASSWORD,
            },
        )
        check(duplicate.status_code == 409, f"a username was taken twice: {duplicate.text}")
        print("duplicate username             409")

        malformed = await client.get(f"{base_url}/charts/property/not-an-id", headers=player)
        check(malformed.status_code == 400, f"malformed id: {malformed.status_code}")
        anonymous = await client.get(f"{base_url}/portfolio/summary")
        check(anonymous.status_code == 401, f"no credential: {anonymous.status_code}")
        print("malformed id / no credential   400 and 401")

    print("\nevery smoke check passed")


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    try:
        asyncio.run(run(base_url.rstrip("/")))
    except SmokeFailure as failure:
        print(f"\nSMOKE CHECK FAILED: {failure}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
