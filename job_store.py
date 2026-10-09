"""In-memory JobStore with TTL eviction and background GC.

Foundation for the publish flow (issue #4). The SSE publish endpoint (#5)
appends events and reads state through this store; the re-attach mechanism
also reads events from here. In-memory only — reboot loses jobs
(documented as out of scope in the spec).

Thread-safety: all public methods acquire a single internal lock. The
background GC thread is a daemon; it can be stopped via stop_gc().

States: pending, running, done, error.
"""

import threading
import time
import uuid


VALID_STATES = ("pending", "running", "done", "error")


class JobStore:
    """Thread-safe in-memory store of jobs with TTL eviction."""

    def __init__(self, ttl_seconds=3600, gc_interval_seconds=300):
        self._jobs = {}  # job_id -> {"events": list, "state": str, "created_at": float}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._gc_interval = gc_interval_seconds
        self._gc_thread = None
        self._stop_event = threading.Event()

    # ---- CRUD --------------------------------------------------------------

    def create(self):
        """Create a new pending job and return its UUID4 string id."""
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "events": [],
                "state": "pending",
                "created_at": time.time(),
            }
        return job_id

    def append_event(self, job_id, event):
        """Append an event dict to the job's event list (preserves order)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job["events"].append(event)

    def get_events(self, job_id):
        """Return a copy of the job's event list. Mutating the result is safe."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return list(job["events"])

    def set_state(self, job_id, state):
        """Set the job's state. ``state`` must be one of VALID_STATES."""
        if state not in VALID_STATES:
            raise ValueError(f"invalid state: {state!r}; must be one of {VALID_STATES}")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job["state"] = state

    def get_state(self, job_id):
        """Return the job's current state string."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job["state"]

    # ---- TTL / GC ----------------------------------------------------------

    def sweep(self):
        """Remove jobs older than TTL. Returns the number evicted."""
        cutoff = time.time() - self._ttl
        with self._lock:
            stale = [jid for jid, job in self._jobs.items() if job["created_at"] < cutoff]
            for jid in stale:
                del self._jobs[jid]
        return len(stale)

    def start_gc(self):
        """Start the background GC daemon thread. Idempotent."""
        if self._gc_thread is not None and self._gc_thread.is_alive():
            return
        self._stop_event.clear()
        thread = threading.Thread(target=self._gc_loop, daemon=True)
        self._gc_thread = thread
        thread.start()

    def stop_gc(self, timeout=2.0):
        """Stop the background GC thread. Safe to call when never started."""
        if self._gc_thread is None:
            return
        self._stop_event.set()
        self._gc_thread.join(timeout=timeout)
        self._gc_thread = None

    def _gc_loop(self):
        while not self._stop_event.is_set():
            # wait() is interruptible by set(); sleep() is not.
            if self._stop_event.wait(self._gc_interval):
                break
            try:
                self.sweep()
            except Exception:
                # Never let GC crash the daemon thread.
                pass
