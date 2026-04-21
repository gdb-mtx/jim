"""Shared notification helpers.

Currently macOS-only via osascript — matches the pattern established in
`scripts/filter_check.py`. Set `FIRE_DISABLE_NOTIFICATIONS=1` to silence
(tests, CI, headless deploys).

Called from:
- `execution/risk_manager.py` state transitions (drawdown alert breach/recovery,
  catastrophe halt)
- `scripts/filter_check.py` (filter changes, daily DD heartbeat)
"""

import logging
import os
import subprocess

log = logging.getLogger("fire.notify")


def notify_macos(title: str, message: str) -> bool:
    """Send a macOS notification. Returns True on success, False if skipped/failed.

    Never raises — a notification failure should never block trading logic.
    """
    if os.environ.get("FIRE_DISABLE_NOTIFICATIONS"):
        return False
    # Escape embedded double quotes so the AppleScript literal stays well-formed.
    safe_title = title.replace('"', "'")
    safe_message = message.replace('"', "'")
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_message}" with title "{safe_title}"',
            ],
            timeout=5,
            check=False,
        )
        return True
    except FileNotFoundError:
        log.debug("osascript not found — skipping notification (non-macOS host?)")
        return False
    except Exception as e:
        log.warning(f"Notification failed: {e}")
        return False
