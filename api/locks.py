"""Shared async locks for rebalance concurrency control."""

import asyncio

_rebalance_locks: dict[int, asyncio.Lock] = {}


def get_rebalance_lock(account: int) -> asyncio.Lock:
    """Get or create a per-account rebalance lock."""
    if account not in _rebalance_locks:
        _rebalance_locks[account] = asyncio.Lock()
    return _rebalance_locks[account]
