"""Put the read path under load and report what it does, in numbers.

The point is not a benchmark to admire. It is to know which of the three things
the scorecard asks about breaks first: the connection pool, memory, or an
unbounded list. Every number this prints comes from a real request against a
running stack.

Concurrency is bounded by a semaphore rather than firing every request at once,
because an unbounded fan-out measures how fast a client can exhaust its own
sockets, not how fast the server answers.

Usage:
    python -m scripts.load [base-url] [--users N] [--requests N] [--token JWT]

Login is rate limited, as it should be, so repeated runs need `--token` with a
token obtained once. The script will not turn the limiter off to measure
around it.
"""

import argparse
import asyncio
import statistics
import time

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"

# The read path a player actually exercises: the market they browse, and the
# two portfolio views the interface loads on every refresh.
ROUTES = (
    "/trading/listings?limit=50",
    "/trading/listings?limit=50&page=3&sortBy=surface&sortOrder=desc",
    "/portfolio/summary",
    "/portfolio/holdings",
)


def percentile(samples: list[float], fraction: float) -> float:
    """The sample at `fraction` through a sorted list, 0.95 meaning p95."""
    if not samples:
        return 0.0
    index = max(0, min(len(samples) - 1, round(fraction * len(samples)) - 1))
    return samples[index]


async def _login(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    )
    if response.status_code == 429:
        raise SystemExit(
            "login is rate limited after several runs, which is the limiter doing its "
            "job. Obtain one token and pass it with --token instead of logging in again."
        )
    response.raise_for_status()
    return response.json()["access_token"]


async def run(base_url: str, users: int, requests: int, token: str | None = None) -> int:
    if token is None:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            token = await _login(client)

    headers = {"Authorization": f"Bearer {token}"}
    limiter = asyncio.Semaphore(users)
    latencies: list[float] = []
    failures: list[str] = []

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=30.0,
        # The pool has to be able to hold every in-flight request, or the
        # measurement is of the client queueing rather than the server working.
        limits=httpx.Limits(max_connections=users, max_keepalive_connections=users),
    ) as client:

        async def one(index: int) -> None:
            route = ROUTES[index % len(ROUTES)]
            async with limiter:
                start = time.perf_counter()
                try:
                    response = await client.get(route)
                # Every failure is reported below, not swallowed: a load run
                # that hides connection errors measures nothing.
                except Exception as error:
                    failures.append(f"{route}: {type(error).__name__}")
                    return
                latencies.append((time.perf_counter() - start) * 1000)
                if response.status_code != 200:
                    failures.append(f"{route}: HTTP {response.status_code}")

        # Warm up so import and connection cost is not reported as latency.
        await asyncio.gather(*(one(i) for i in range(min(users, requests))))
        latencies.clear()
        failures.clear()

        started = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(requests)))
        elapsed = time.perf_counter() - started

    latencies.sort()
    print(f"{requests} requests over {users} concurrent callers, {elapsed:.1f} s")
    print(f"  throughput   {requests / elapsed:8.1f} req/s")
    print(f"  p50          {percentile(latencies, 0.50):8.1f} ms")
    print(f"  p95          {percentile(latencies, 0.95):8.1f} ms")
    print(f"  p99          {percentile(latencies, 0.99):8.1f} ms")
    print(f"  max          {max(latencies, default=0.0):8.1f} ms")
    print(f"  mean         {statistics.fmean(latencies) if latencies else 0.0:8.1f} ms")
    print(f"  failures     {len(failures):8d}")
    for failure in sorted(set(failures))[:5]:
        print(f"      {failure}")

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--users", type=int, default=50, help="concurrent callers")
    parser.add_argument("--requests", type=int, default=2000, help="total requests")
    parser.add_argument("--token", help="reuse a token instead of logging in again")
    arguments = parser.parse_args()
    return asyncio.run(
        run(arguments.base_url, arguments.users, arguments.requests, arguments.token)
    )


if __name__ == "__main__":
    raise SystemExit(main())
