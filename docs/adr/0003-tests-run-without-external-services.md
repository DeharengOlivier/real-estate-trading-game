# 3. The test suite runs with no MongoDB and no Redis

Date: 2026-08-29

## Status

Accepted.

## Context

The application depends on MongoDB and Redis. A test suite can get them from a
real server, from a container started for the run, or from an in-process
substitute. The choice decides how long the feedback loop is, what CI has to
provision, and which code paths can be tested at all.

## Decision

Substitute both in process: `mongomock-motor` for MongoDB and `fakeredis` for
Redis, wired through fixtures in `api/tests/conftest.py`. `pytest` on a bare
virtual environment runs the whole suite with nothing else running.

The guards that a substitute cannot prove are checked separately, against the
real stack, by `scripts/smoke.py`: the admin refusal, the clock refusal, two
buyers racing for one listing, non-negative balances, the duplicate-registration
409 and the malformed-identifier 400. CI starts the compose stack and runs it.

## Consequences

**What this buys.** 244 tests in about 45 seconds with no services to start,
which is short enough that the suite is actually run between edits. CI needs no
service containers for the unit job, and a contributor can run everything on a
laptop with one `pip install`.

**What this costs.** The substitute is not the database. Two things follow:

- Transactions are unavailable, which is one of the two reasons
  [0001](0001-conditional-writes-instead-of-transactions.md) does not use them.
- `mongomock` and `pymongo` drift. `pymongo` 4.11 began passing a `sort`
  argument to the bulk-write builder that `mongomock` 4.3.0 rejects, which is
  why `api/requirements.txt` pins `pymongo==4.10.1` with the condition for
  removing the pin written next to it.

**What would change this decision.** A test that needs a real transaction, a
real index constraint under concurrency, or a real aggregation operator. The
first two already exist as smoke checks against the compose stack; if there are
enough of them to be a suite rather than a script, move the boundary tests onto
a `mongo` service container and keep the substitutes for the fast unit layer.
