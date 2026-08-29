"""The quarter advance must not hold the whole catalogue in memory.

Measured before the fix, with tracemalloc around one call to advance_quarter:

      500 properties -> peak   1.3 MiB
     2000 properties -> peak   4.7 MiB

That is roughly 2.4 KiB per property, held inside a single request, because the
handler read every property into one list, built one dict per property from it,
and then built one UpdateOne per property from that. A 300 000-property
catalogue would ask for something near 700 MiB before answering.

Batching the writes was not enough on its own. Measured again against a real
MongoDB, the peak was 2.3 / 23.0 / 114.8 MiB for 2 000 / 20 000 / 100 000
properties and did not move when the flush size was changed from 50 to 5 000:
the driver fills a cursor batch up to 16 MB, so `async for` reads like
streaming while tens of thousands of documents are already materialised. With
`batch_size` set as well, the same runs peak at 0.7 / 0.7 / 0.8 MiB, and the
peak follows the constant instead (0.3 MiB at 50, 7.0 MiB at 5 000).

So there are two things to hold, and both are tested here: the writes are
flushed in fixed-size batches, and the cursor is told how much to hold.
"""

import pytest

import api.routers.game as game_router
from api.database import get_database
from api.routers.game import PRICE_UPDATE_BATCH, advance_quarter
from simulation.constants import ZONES

# Comfortably more than one batch, so a per-batch bound and a whole-catalogue
# bound cannot both pass.
CATALOGUE = PRICE_UPDATE_BATCH * 2 + 7

ADMIN = {"_id": "admin-id", "username": "admin", "roles": ["user", "admin"]}


async def _fill_catalogue(db, count):
    """Insert `count` priced, listed properties and return their ids."""
    properties = [
        {
            "zone": ZONES[index % len(ZONES)],
            "type": "apartment",
            "surface": 80.0,
            "epc": 0.5,
            "state": 0.5,
            "kitchen": 0.5,
            "bath": 0.5,
            "base_ppm": 3000,
        }
        for index in range(count)
    ]
    if not properties:
        return []
    result = await db.properties.insert_many(properties)
    await db.listings.insert_many(
        [
            {"propertyId": property_id, "isAvailable": True, "lastComputedPrice": 1.0}
            for property_id in result.inserted_ids
        ]
    )
    return result.inserted_ids


class _RecordingCollection:
    """Forward every call, recording how large the batched writes were."""

    _BATCHED = ("insert_many", "bulk_write")

    def __init__(self, collection, sizes, name):
        self._collection = collection
        self._sizes = sizes
        self._name = name

    def __getattr__(self, attribute):
        target = getattr(self._collection, attribute)
        if attribute not in self._BATCHED:
            return target

        def recording(items, *args, **kwargs):
            items = list(items)
            self._sizes.setdefault(f"{self._name}.{attribute}", []).append(len(items))
            return target(items, *args, **kwargs)

        return recording


class _RecordingDatabase:
    """A database that records the size of every batched write made through it."""

    def __init__(self, db, sizes):
        self._db = db
        self._sizes = sizes

    def __getattr__(self, name):
        return _RecordingCollection(getattr(self._db, name), self._sizes, name)

    def __getitem__(self, name):
        return _RecordingCollection(self._db[name], self._sizes, name)


@pytest.fixture
def batch_sizes(monkeypatch):
    """Record the size of every write batch the quarter advance sends."""
    sizes = {}
    monkeypatch.setattr(
        game_router, "get_database", lambda: _RecordingDatabase(get_database(), sizes)
    )
    return sizes


def _largest(sizes):
    """The biggest single batch handed to the database, across every collection."""
    batches = [size for recorded in sizes.values() for size in recorded]
    assert batches, "no batched write was recorded; the fixture is not intercepting"
    return max(batches)


@pytest.mark.asyncio
async def test_no_write_batch_exceeds_the_configured_size(batch_sizes):
    """The exact defect: one write carrying one entry per property in the game."""
    db = get_database()
    await _fill_catalogue(db, CATALOGUE)

    await advance_quarter(current_user=ADMIN)

    largest = _largest(batch_sizes)
    assert largest <= PRICE_UPDATE_BATCH, (
        f"a single write carried {largest} entries for {CATALOGUE} properties; "
        f"the bound is {PRICE_UPDATE_BATCH}"
    )


@pytest.mark.asyncio
async def test_the_bound_holds_when_the_catalogue_doubles(batch_sizes):
    """The invariant, stated generally: the batch size does not follow the data."""
    db = get_database()
    await _fill_catalogue(db, CATALOGUE * 2)

    await advance_quarter(current_user=ADMIN)

    assert _largest(batch_sizes) <= PRICE_UPDATE_BATCH


@pytest.mark.asyncio
async def test_every_property_is_still_repriced_exactly_once():
    """Batching must not lose or duplicate a property on a batch boundary."""
    db = get_database()
    property_ids = await _fill_catalogue(db, CATALOGUE)

    result = await advance_quarter(current_user=ADMIN)
    next_t = result["quarter"]

    assert result["propertiesUpdated"] == CATALOGUE
    rows = await db.pricehistory.find({"t": next_t}).to_list(length=None)
    assert len(rows) == CATALOGUE
    assert {row["propertyId"] for row in rows} == set(property_ids)

    listings = await db.listings.find({}).to_list(length=None)
    assert all(listing["lastT"] == next_t for listing in listings)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2])
async def test_a_catalogue_smaller_than_one_batch_still_advances(count):
    """Boundaries: nothing to price, and less than a full batch to price."""
    db = get_database()
    await _fill_catalogue(db, count)

    result = await advance_quarter(current_user=ADMIN)

    assert result["propertiesUpdated"] == count
    rows = await db.pricehistory.find({"t": result["quarter"]}).to_list(length=None)
    assert len(rows) == count


@pytest.mark.asyncio
async def test_the_property_cursor_is_told_how_much_to_hold(monkeypatch):
    """Without batch_size the driver materialises the catalogue behind the loop.

    mongomock cannot show that in memory, so what is pinned here is the call
    itself: dropping it puts the peak back on the catalogue size, silently.
    """
    db = get_database()
    await _fill_catalogue(db, 3)

    requested = []
    original_find = db.properties.find

    def recording_find(*args, **kwargs):
        cursor = original_find(*args, **kwargs)
        original_batch_size = cursor.batch_size

        def recording_batch_size(size):
            requested.append(size)
            return original_batch_size(size)

        cursor.batch_size = recording_batch_size
        return cursor

    class _Properties:
        def __getattr__(self, name):
            return recording_find if name == "find" else getattr(db.properties, name)

    class _Database:
        def __getattr__(self, name):
            return _Properties() if name == "properties" else getattr(db, name)

    monkeypatch.setattr(game_router, "get_database", _Database)

    await advance_quarter(current_user=ADMIN)

    assert requested == [PRICE_UPDATE_BATCH], (
        "the property cursor was not bounded; without batch_size the driver "
        "holds as many documents as fit in one 16 MB server batch"
    )


@pytest.mark.asyncio
async def test_a_catalogue_of_exactly_one_batch_flushes_once(batch_sizes):
    """The off-by-one: a full batch must not be flushed twice, nor left unflushed."""
    db = get_database()
    await _fill_catalogue(db, PRICE_UPDATE_BATCH)

    await advance_quarter(current_user=ADMIN)

    assert batch_sizes["pricehistory.insert_many"] == [PRICE_UPDATE_BATCH]
    assert batch_sizes["listings.bulk_write"] == [PRICE_UPDATE_BATCH]
