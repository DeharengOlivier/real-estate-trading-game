# 1. Money moves with conditional writes, not with transactions

Date: 2026-08-29

## Status

Accepted.

## Context

Buying a property touches four collections: the listing has to leave the
market, a holding has to appear, cash has to be debited, and a trade record has
to be written. Selling does the reverse. Two things in there are scarce and can
be claimed twice if the code reads a value, decides in Python, and writes the
result back:

- the listing, if two buyers pass the `isAvailable` check before either writes;
- the cash, if two purchases both read a balance that covers them.

The original implementation opened a MongoDB session, tried to start a
transaction, and fell back to plain writes when the server refused. The
development and demonstration stack is a single `mongo:7` container, which is a
standalone node, and a standalone node has no transactions. So the fallback was
the only path that ever ran, and the code that was supposed to make trades
atomic was never once executed.

## Decision

Do not use multi-document transactions. Put the precondition of every scarce
claim inside the filter of a single atomic write, and compensate explicitly
when a later step fails.

- The listing is claimed with `find_one_and_update({propertyId, isAvailable:
  true}, {$set: {isAvailable: false}})`. Exactly one of two simultaneous buyers
  gets a document back; the other gets `None` and a 404.
- Cash is debited with `find_one_and_update({_id, cash: {$gte: total}}, {$inc:
  {cash: -total}})`. The balance is read and written in one operation, so it
  cannot go negative however many requests arrive at once.
- The holding is claimed on sale with `find_one_and_delete`. Whoever removes it
  is the one who gets paid.
- A buyer who cannot pay has the listing released and the holding removed
  before the 400 is raised.

## Consequences

**What this buys.** The guarantees hold on a standalone node, which is what the
project actually ships, and they are exercised by every test run rather than by
a code path that only exists in production. `api/tests/test_trading_concurrency.py`
drives two buyers into the same listing through a rendezvous and asserts that
one wins, one is refused, the balance is debited once and exactly one buy trade
exists. Run against the pre-fix implementation, five of its seven cases fail.

**What this does not buy.** The four writes of a purchase are still four
writes. A process killed between the holding insert and the cash debit leaves a
holding that was never paid for. The order is chosen so that this is the side
the failure falls on: a property nobody was charged for is recoverable by
hand, a charge for nothing is money taken from a player.

**What would change this decision.** Running MongoDB as a single-node replica
set would make transactions available and close that window. It was not done
because the whole test suite runs on `mongomock-motor`, which has no
transaction support, so the transactional path would once again be code that
never runs where it is tested. Revisit this together with
[0003](0003-tests-run-without-external-services.md): the two decisions are one
decision.
