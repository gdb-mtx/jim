"""Shared test fixtures.

The autouse fixture below is load-bearing: without it, unit tests that
exercise the rebalance path read (and could WRITE) the real
`data/risk_state/expected_positions_acct*.json` files — mock brokers
report zero positions, real expected-position state says otherwise, and
position reconciliation correctly blocks the "rebalance", failing the
test against live operational state. Discovered 2026-07-18 when the real
A1 book started leaking into test assertions.
"""

import pytest


@pytest.fixture(autouse=True)
def isolate_reconciliation_state(tmp_path, monkeypatch):
    """Point position-reconciliation state at a per-test temp dir."""
    import execution.position_reconciliation as recon

    monkeypatch.setattr(recon, "STATE_DIR", tmp_path)
    yield
