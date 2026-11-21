"""Retention maintenance of the practice interview (docs/DECISIONS.md D53): settle the sessions past their deadline, delete the
expired ones with their turns, and delete the daily-quota rows of past days.

    python scripts/purge_interviews.py [--dry-run] [--batch N]

Nothing in the app runs this on a schedule. Expired sessions are hidden from every read as soon as they expire, and the app
deletes some of them as a side effect of creating a session or listing the history, but only a scheduler that runs this script
(cron, Windows Task Scheduler, or `docker compose run --rm backend python scripts/purge_interviews.py` from the host) deletes
them all. Until a deployment configures one, do not say that deleted-after-30-days happens automatically.

`--dry-run` changes nothing and only counts. The output and the log are counts only: no transcript, feedback or id.
Safe to run again and to run at the same time as the app or another run.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.db.session import SessionLocal  # noqa: E402
from app.services import interview_service  # noqa: E402


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def main(argv: list[str] | None = None, *, session_factory=None, clock=None) -> int:
    """`session_factory` and `clock` are test seams, not command-line options. Without a clock the real one is used, which is what a
    scheduled run needs: `clock` is passed on only when it is given, so the command line behaves exactly as before."""
    parser = argparse.ArgumentParser(description="Settle stale practice interviews and delete expired ones.")
    parser.add_argument("--dry-run", action="store_true", help="only count what would be settled and deleted")
    parser.add_argument("--batch", type=_positive, default=500, help="expired sessions deleted per transaction (default 500)")
    args = parser.parse_args(argv)
    options = {} if clock is None else {"clock": clock}
    with (session_factory or SessionLocal)() as db:
        report = interview_service.maintenance(db, batch=args.batch, dry_run=args.dry_run, **options)
    if report.dry_run:
        print(f"dry run, nothing changed: would_settle={report.settled} would_purge_sessions={report.purged_sessions} would_purge_quota_rows={report.purged_quota_rows}")
    else:
        print(f"settled={report.settled} purged_sessions={report.purged_sessions} purged_quota_rows={report.purged_quota_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
