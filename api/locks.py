"""Shared locks for rebalance concurrency control.

Two layers:
- AsyncIO locks for in-process concurrency (FastAPI async handlers)
- File locks for cross-process concurrency (filter_check.py cron vs server)
"""

import asyncio
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

_rebalance_locks: dict[int, asyncio.Lock] = {}

LOCK_DIR = Path(__file__).parent.parent / "data" / "risk_state"


def get_rebalance_lock(account: int) -> asyncio.Lock:
    """Get or create a per-account async rebalance lock (in-process)."""
    if account not in _rebalance_locks:
        _rebalance_locks[account] = asyncio.Lock()
    return _rebalance_locks[account]


@contextmanager
def file_rebalance_lock(account: int):
    """Cross-process file lock for rebalance. Non-blocking — raises if locked.

    Usage:
        with file_rebalance_lock(account=1):
            # exclusive rebalance access
            ...

    Raises OSError if another process holds the lock.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"rebalance_lock_acct{account}.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
