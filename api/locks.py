"""Shared locks for rebalance + snapshot concurrency control.

Two layers:
- AsyncIO locks for in-process concurrency (FastAPI async handlers)
- File locks for cross-process concurrency (filter_check.py cron vs server)

`dual_rebalance_lock` bundles both into a single context manager so every
rebalance entry point (API endpoint, APScheduler job, filter cron) is
guaranteed to serialize against every other — closes AUDIT_MONTH2.md S1.

`file_snapshot_lock` serializes snapshot read-modify-write across the four
concurrent callers (filter cron, dashboard /snapshot, post-rebalance hook,
server startup) — closes AUDIT_MONTH2.md S3.
"""

import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

_rebalance_locks: dict[int, asyncio.Lock] = {}

LOCK_DIR = Path(__file__).parent.parent / "data" / "risk_state"


class RebalanceLockedError(OSError):
    """Raised when another rebalance is already in progress for the account.

    Subclasses OSError so existing `except OSError` handlers (filter_check.py)
    keep working unchanged.
    """


def get_rebalance_lock(account: int) -> asyncio.Lock:
    """Get or create a per-account async rebalance lock (in-process)."""
    if account not in _rebalance_locks:
        _rebalance_locks[account] = asyncio.Lock()
    return _rebalance_locks[account]


def _rebalance_lock_path(account: int) -> Path:
    return LOCK_DIR / f"rebalance_lock_acct{account}.lock"


def _snapshot_lock_path(account: int) -> Path:
    return LOCK_DIR / f"snapshot_lock_acct{account}.lock"


def _acquire_file_lock_nb(path: Path) -> int:
    """Non-blocking exclusive file lock. Returns fd or raises OSError."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _acquire_file_lock_blocking(path: Path, timeout: float) -> int:
    """Blocking exclusive file lock with timeout. Returns fd or raises OSError."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
    except BaseException:
        os.close(fd)
        raise


def _release_file_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def file_rebalance_lock(account: int):
    """Cross-process file lock for rebalance. Non-blocking — raises if locked.

    Usage (sync callers like scripts/filter_check.py):
        with file_rebalance_lock(account=1):
            # exclusive rebalance access
            ...

    Raises OSError if another process holds the lock. Async callers should
    use `dual_rebalance_lock` instead.
    """
    fd = _acquire_file_lock_nb(_rebalance_lock_path(account))
    try:
        yield
    finally:
        _release_file_lock(fd)


@asynccontextmanager
async def dual_rebalance_lock(account: int):
    """Take both the in-process async lock and the cross-process file lock.

    Every async rebalance path (API endpoint, APScheduler job) must use this
    so it serializes against (a) concurrent requests in the same server and
    (b) the filter_check.py cron holding only the file lock.

    Raises RebalanceLockedError (a subclass of OSError) if either lock is
    held — callers translate that into a 409 response or a log-and-skip.

    The file lock is acquired in a thread to avoid blocking the event loop
    on the (cheap, non-blocking) fcntl call.
    """
    async_lock = get_rebalance_lock(account)
    if async_lock.locked():
        raise RebalanceLockedError(
            f"rebalance already in progress (in-process) for account {account}"
        )
    async with async_lock:
        try:
            fd = await asyncio.to_thread(
                _acquire_file_lock_nb, _rebalance_lock_path(account)
            )
        except OSError as e:
            raise RebalanceLockedError(
                f"rebalance already in progress (another process) for account {account}"
            ) from e
        try:
            yield
        finally:
            await asyncio.to_thread(_release_file_lock, fd)


@contextmanager
def file_snapshot_lock(account: int, timeout: float = 10.0):
    """Blocking per-account snapshot lock with timeout.

    Unlike the rebalance lock, concurrent snapshot writers are legitimate —
    filter cron + dashboard /snapshot + post-rebalance hook can all fire at
    once. We serialize rather than fail-fast. Raises OSError if the lock
    can't be acquired within `timeout` seconds.

    Sync usage:
        with file_snapshot_lock(account):
            save_snapshot(...)

    Async callers: wrap the whole critical section in `asyncio.to_thread`.
    """
    fd = _acquire_file_lock_blocking(_snapshot_lock_path(account), timeout)
    try:
        yield
    finally:
        _release_file_lock(fd)
