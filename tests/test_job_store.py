"""Tests for the in-memory JobStore (issue #4)."""

import sys
import threading
import time
import uuid
from pathlib import Path

import pytest


WORKTREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))


# --- Cycle 1: CRUD ----------------------------------------------------------


def test_create_returns_unique_uuid_strings():
    """create() returns distinct UUID4 strings; each can be used to look up the job."""
    from job_store import JobStore

    store = JobStore()
    job_id_1 = store.create()
    job_id_2 = store.create()
    assert job_id_1 != job_id_2
    # UUID4 string form: 8-4-4-4-12 hex chars
    uuid.UUID(job_id_1)
    uuid.UUID(job_id_2)


def test_new_job_starts_in_pending_state_with_empty_events():
    """A newly created job has state=pending and events=[]."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()
    assert store.get_state(job_id) == "pending"
    assert store.get_events(job_id) == []


def test_append_event_adds_to_job_event_list_in_order():
    """append_event stores events in append order."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()
    store.append_event(job_id, {"type": "started", "data": {"job_id": job_id}})
    store.append_event(job_id, {"type": "generating", "data": {"frame": "1/8"}})
    store.append_event(job_id, {"type": "completed", "data": {"publish_id": "v2.x"}})
    assert store.get_events(job_id) == [
        {"type": "started", "data": {"job_id": job_id}},
        {"type": "generating", "data": {"frame": "1/8"}},
        {"type": "completed", "data": {"publish_id": "v2.x"}},
    ]


def test_set_state_updates_job_state():
    """set_state transitions the job to the new state."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()
    store.set_state(job_id, "running")
    assert store.get_state(job_id) == "running"
    store.set_state(job_id, "done")
    assert store.get_state(job_id) == "done"


def test_get_events_returns_a_copy_not_a_reference():
    """get_events returns a list that, when mutated, does not affect internal state."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()
    store.append_event(job_id, {"type": "started"})
    events = store.get_events(job_id)
    events.append({"type": "rogue"})
    assert store.get_events(job_id) == [{"type": "started"}]


def test_operations_on_unknown_job_raise_keyerror():
    """append_event, get_events, set_state, get_state on an unknown job_id raise KeyError."""
    from job_store import JobStore

    store = JobStore()
    with pytest.raises(KeyError):
        store.append_event("not-a-real-job", {"type": "x"})
    with pytest.raises(KeyError):
        store.get_events("not-a-real-job")
    with pytest.raises(KeyError):
        store.set_state("not-a-real-job", "done")
    with pytest.raises(KeyError):
        store.get_state("not-a-real-job")


# --- Cycle 2: TTL eviction --------------------------------------------------


def test_sweep_evicts_jobs_older_than_ttl():
    """sweep() removes jobs whose created_at is older than the TTL."""
    from job_store import JobStore

    # 10s TTL so we can age the job deterministically
    store = JobStore(ttl_seconds=10)
    old_id = store.create()
    new_id = store.create()

    # Manually backdate the old job
    store._jobs[old_id]["created_at"] = time.time() - 100

    evicted = store.sweep()
    assert evicted == 1
    assert old_id not in store._jobs
    assert new_id in store._jobs
    # The new job is still queryable normally
    assert store.get_state(new_id) == "pending"


def test_sweep_returns_zero_when_nothing_to_evict():
    """sweep() returns 0 when no jobs are older than the TTL."""
    from job_store import JobStore

    store = JobStore(ttl_seconds=3600)
    store.create()
    assert store.sweep() == 0


def test_sweep_is_safe_to_call_with_no_jobs():
    """sweep() on an empty store returns 0 without error."""
    from job_store import JobStore

    assert JobStore().sweep() == 0


# --- Cycle 3: thread-safety -------------------------------------------------


def test_concurrent_appends_preserve_all_events():
    """Multiple threads appending events concurrently all events are recorded in order."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()

    def append_n(n_start, n_count):
        for i in range(n_start, n_start + n_count):
            store.append_event(job_id, {"type": "ev", "n": i})

    # 4 threads, each appending 50 distinct n values starting at 0, 50, 100, 150.
    threads = [threading.Thread(target=append_n, args=(i * 50, 50)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = store.get_events(job_id)
    assert len(events) == 200
    # All n values present (set equality)
    seen = {e["n"] for e in events}
    assert seen == set(range(200))


def test_concurrent_set_state_is_safe():
    """Multiple threads setting state concurrently end up with a valid state value."""
    from job_store import JobStore

    store = JobStore()
    job_id = store.create()
    states = ["running", "done", "error", "pending"]

    def set_random_state():
        for _ in range(100):
            store.set_state(job_id, states[hash(threading.current_thread().name) % 4])

    threads = [threading.Thread(target=set_random_state) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No crash, final state is one of the valid values
    assert store.get_state(job_id) in states


# --- Cycle 4: GC thread lifecycle ------------------------------------------


def test_start_gc_starts_a_daemon_thread_that_can_be_stopped():
    """start_gc launches a daemon thread; stop_gc joins it."""
    from job_store import JobStore

    store = JobStore(ttl_seconds=1, gc_interval_seconds=1)
    store.start_gc()
    assert store._gc_thread is not None
    assert store._gc_thread.is_alive()
    assert store._gc_thread.daemon is True
    store.stop_gc()
    assert store._gc_thread is None or not store._gc_thread.is_alive()


def test_start_gc_is_idempotent():
    """start_gc called twice does not spawn a second thread."""
    from job_store import JobStore

    store = JobStore()
    store.start_gc()
    first_thread = store._gc_thread
    store.start_gc()  # second call should be a no-op
    assert store._gc_thread is first_thread
    store.stop_gc()


def test_stop_gc_is_safe_to_call_when_never_started():
    """stop_gc on a store that never started GC is a no-op."""
    from job_store import JobStore

    JobStore().stop_gc()  # should not raise


def test_gc_thread_eventually_evicts_old_jobs(monkeypatch):
    """A job older than TTL is evicted by the GC thread (using a short interval)."""
    from job_store import JobStore

    # 1s TTL, 1s GC interval — wait ~2.5s for a sweep to fire and evict
    store = JobStore(ttl_seconds=1, gc_interval_seconds=1)
    job_id = store.create()
    # Backdate so it's already expired by the time GC runs
    store._jobs[job_id]["created_at"] = time.time() - 5
    store.start_gc()
    try:
        # Poll for eviction
        deadline = time.time() + 3
        while time.time() < deadline:
            if job_id not in store._jobs:
                break
            time.sleep(0.1)
        assert job_id not in store._jobs
    finally:
        store.stop_gc()
