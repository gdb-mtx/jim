#!/bin/bash
# Wrapper for launchd — /bin/bash is Apple-signed so launchd won't
# block it as "Unknown Developer." Delegates to uv immediately.
exec /Users/george/.local/bin/uv run python3 /Users/george/Desktop/Projects/FIRE/scripts/daily_crypto_rebalance.py
