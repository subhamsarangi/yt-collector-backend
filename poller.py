"""
Queue poller — runs as a separate systemd service on OCI.
Polls Supabase every 10 seconds for pending/yt_dlp_done queue items
and triggers the Vercel queue runner when found.
Replaces the fragile HTTP self-call chain in the Vercel functions.
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [poller] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

VERCEL_URL = os.environ["NEXT_PUBLIC_APP_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["QUEUE_WEBHOOK_SECRET"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

POLL_INTERVAL = 10  # seconds between polls
TRIGGER_TIMEOUT = 10  # seconds to wait for Vercel to accept the trigger

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

ACTIVE_STATUSES = {"yt_dlp_processing", "whisper_processing", "whisper_done"}
WORKABLE_STATUSES = {"pending", "yt_dlp_done"}


def get_queue_state() -> dict:
    """Return counts of active and workable queue items."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/queue",
            headers=HEADERS,
            params={
                "select": "status",
                "status": f"in.({','.join(ACTIVE_STATUSES | WORKABLE_STATUSES)})",
            },
            timeout=8,
        )
        r.raise_for_status()
        rows = r.json()
        active = sum(1 for row in rows if row["status"] in ACTIVE_STATUSES)
        workable = sum(1 for row in rows if row["status"] in WORKABLE_STATUSES)
        return {"active": active, "workable": workable}
    except Exception as e:
        log.warning(f"Supabase poll failed: {e}")
        return {"active": 0, "workable": 0}


def trigger_runner() -> bool:
    """POST to Vercel queue runner. Returns True if accepted."""
    try:
        r = requests.post(
            f"{VERCEL_URL}/api/cron/queue-runner",
            headers={"x-webhook-secret": WEBHOOK_SECRET},
            timeout=TRIGGER_TIMEOUT,
        )
        log.info(f"Triggered queue runner → {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        log.warning(f"Trigger failed: {e}")
        return False


def main():
    log.info(f"Poller started — polling every {POLL_INTERVAL}s → {VERCEL_URL}")
    consecutive_failures = 0

    while True:
        try:
            state = get_queue_state()

            if state["active"] > 0:
                log.info(
                    f"Job in progress ({state['active']} active) — skipping trigger"
                )
            elif state["workable"] > 0:
                log.info(f"{state['workable']} item(s) waiting — triggering runner")
                ok = trigger_runner()
                if not ok:
                    consecutive_failures += 1
                    log.warning(f"Trigger failed ({consecutive_failures} consecutive)")
                else:
                    consecutive_failures = 0
            # else: queue empty, nothing to do

        except Exception as e:
            log.error(f"Unexpected error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
