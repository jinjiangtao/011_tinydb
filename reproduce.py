"""Reproduce the CachingMiddleware + query cache consistency issue."""

from tinydb import TinyDB, where
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage, JSONStorage
import tempfile, os

def test_basic_insert_search():
    """Basic insert then search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    for i in range(10):
        db.insert({'value': i})

    results = db.search(where('value') >= 0)
    assert len(results) == 10, f"Expected 10, got {len(results)}"
    print("PASS: test_basic_insert_search")

def test_insert_search_insert_search():
    """Interleaved insert and search — exercises query cache."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert({'value': 1})

    r1 = db.search(where('value') >= 1)
    assert len(r1) == 1, f"r1: Expected 1, got {len(r1)}"

    db.insert({'value': 2})
    r2 = db.search(where('value') >= 1)
    assert len(r2) == 2, f"r2: Expected 2, got {len(r2)}"

    db.insert({'value': 3})
    r3 = db.search(where('value') >= 1)
    assert len(r3) == 3, f"r3: Expected 3, got {len(r3)}"
    print("PASS: test_insert_search_insert_search")

def test_insert_multiple_then_search():
    """insert_multiple followed by search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert_multiple([{'value': i} for i in range(20)])

    results = db.search(where('value') >= 0)
    assert len(results) == 20, f"Expected 20, got {len(results)}"

    # Now update some and search again
    db.update({'updated': True}, where('value') >= 10)

    updated = db.search(where('updated') == True)
    assert len(updated) == 10, f"Expected 10 updated, got {len(updated)}"

    # Original query should still find all 20
    all_results = db.search(where('value') >= 0)
    assert len(all_results) == 20, f"Expected 20 total, got {len(all_results)}"
    print("PASS: test_insert_multiple_then_search")

def test_update_then_search():
    """Update data then search — the exact scenario user described."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert_multiple([{'name': f'user{i}', 'age': 20 + i} for i in range(10)])

    # Search for young users
    young = db.search(where('age') < 25)
    assert len(young) == 5, f"Expected 5 young users, got {len(young)}"

    # Update: make everyone older by 10
    db.update({'age': 30}, where('age') < 25)

    # Search again — should find 0 young users now
    young_after = db.search(where('age') < 25)
    assert len(young_after) == 0, f"Expected 0 young users after update, got {len(young_after)}"

    # Search for age=30 should find the 5 updated users
    age30 = db.search(where('age') == 30)
    assert len(age30) == 5, f"Expected 5 users with age=30, got {len(age30)}"
    print("PASS: test_update_then_search")

def test_flush_then_search():
    """Force flush via WRITE_CACHE_SIZE then search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    # Set small cache size to trigger flushes
    db.storage.WRITE_CACHE_SIZE = 3

    for i in range(10):
        db.insert({'value': i})

    results = db.search(where('value') >= 0)
    assert len(results) == 10, f"Expected 10, got {len(results)}"
    print("PASS: test_flush_then_search")

def test_search_cache_stale_after_update():
    """
    Critical test: search, then update, then same search again.
    The query cache MUST be invalidated by the update.
    """
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert({'name': 'Alice', 'active': True})
    db.insert({'name': 'Bob', 'active': True})

    cond = where('active') == True

    # First search — populates query cache
    r1 = db.search(cond)
    assert len(r1) == 2, f"r1: Expected 2, got {len(r1)}"

    # Update Bob to inactive
    db.update({'active': False}, where('name') == 'Bob')

    # Second search — MUST NOT use stale query cache
    r2 = db.search(cond)
    assert len(r2) == 1, f"r2: Expected 1 (only Alice), got {len(r2)}: {r2}"
    assert r2[0]['name'] == 'Alice', f"Expected Alice, got {r2[0]['name']}"
    print("PASS: test_search_cache_stale_after_update")

def test_consecutive_inserts_all_visible():
    """After many consecutive inserts, all should be visible via search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))

    N = 50
    for i in range(N):
        db.insert({'idx': i, 'type': 'A' if i % 2 == 0 else 'B'})

    all_docs = db.search(where('idx') >= 0)
    assert len(all_docs) == N, f"Expected {N}, got {len(all_docs)}"

    type_a = db.search(where('type') == 'A')
    assert len(type_a) == 25, f"Expected 25 type A, got {len(type_a)}"

    type_b = db.search(where('type') == 'B')
    assert len(type_b) == 25, f"Expected 25 type B, got {len(type_b)}"
    print("PASS: test_consecutive_inserts_all_visible")

def test_all_method_after_inserts():
    """db.all() should return all documents after inserts."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))

    for i in range(10):
        db.insert({'value': i})

    all_docs = db.all()
    assert len(all_docs) == 10, f"Expected 10, got {len(all_docs)}"
    print("PASS: test_all_method_after_inserts")

def test_json_storage_consistency():
    """Test with JSONStorage + CachingMiddleware."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, 'test.json')

        with TinyDB(path, storage=CachingMiddleware(JSONStorage)) as db:
            for i in range(10):
                db.insert({'value': i})

            results = db.search(where('value') >= 0)
            assert len(results) == 10, f"Expected 10, got {len(results)}"

            db.update({'updated': True}, where('value') >= 5)

            updated = db.search(where('updated') == True)
            assert len(updated) == 5, f"Expected 5, got {len(updated)}"

        # Reopen and verify data persisted correctly
        with TinyDB(path, storage=CachingMiddleware(JSONStorage)) as db:
            all_docs = db.all()
            assert len(all_docs) == 10, f"After reopen: Expected 10, got {len(all_docs)}"

            updated = db.search(where('updated') == True)
            assert len(updated) == 5, f"After reopen: Expected 5 updated, got {len(updated)}"

    print("PASS: test_json_storage_consistency")

def test_multi_table_cache_isolation():
    """Multiple tables sharing CachingMiddleware — writes to one shouldn't stale the other."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    t1 = db.table('t1')
    t2 = db.table('t2')

    t1.insert({'value': 1})
    t2.insert({'value': 100})

    r1 = t1.search(where('value') >= 0)
    assert len(r1) == 1 and r1[0]['value'] == 1, f"t1 wrong: {r1}"

    r2 = t2.search(where('value') >= 0)
    assert len(r2) == 1 and r2[0]['value'] == 100, f"t2 wrong: {r2}"

    # Insert into t2, search t1
    t2.insert({'value': 200})
    r1_again = t1.search(where('value') >= 0)
    assert len(r1_again) == 1 and r1_again[0]['value'] == 1, f"t1 stale after t2 write: {r1_again}"
    print("PASS: test_multi_table_cache_isolation")

def test_upsert_then_search():
    """Upsert (update-or-insert) then search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert({'name': 'Alice', 'score': 10})

    # Upsert: update Alice's score
    db.upsert({'name': 'Alice', 'score': 20}, where('name') == 'Alice')

    results = db.search(where('score') == 20)
    assert len(results) == 1, f"Expected 1, got {len(results)}"
    assert results[0]['name'] == 'Alice'

    # Upsert: insert new person
    db.upsert({'name': 'Bob', 'score': 15}, where('name') == 'Bob')

    all_docs = db.search(where('score') >= 0)
    assert len(all_docs) == 2, f"Expected 2, got {len(all_docs)}"
    print("PASS: test_upsert_then_search")

def test_remove_then_search():
    """Remove documents then search."""
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    db.insert_multiple([{'value': i} for i in range(5)])

    # Search first to populate query cache
    r1 = db.search(where('value') >= 0)
    assert len(r1) == 5

    # Remove some
    db.remove(where('value') >= 3)

    # Search again
    r2 = db.search(where('value') >= 0)
    assert len(r2) == 3, f"Expected 3 after remove, got {len(r2)}"
    print("PASS: test_remove_then_search")


if __name__ == '__main__':
    test_basic_insert_search()
    test_insert_search_insert_search()
    test_insert_multiple_then_search()
    test_update_then_search()
    test_flush_then_search()
    test_search_cache_stale_after_update()
    test_consecutive_inserts_all_visible()
    test_all_method_after_inserts()
    test_json_storage_consistency()
    test_multi_table_cache_isolation()
    test_upsert_then_search()
    test_remove_then_search()
    print("\nAll tests passed!")
