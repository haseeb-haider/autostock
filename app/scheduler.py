"""Optional in-process scheduler.

On Render's free tier the web service sleeps after 15 min idle, so this will not
fire reliably - the GitHub Action is the dependable trigger. Enabled only when
ENABLE_SCHEDULER=true (useful on an always-on/paid instance)."""
from . import config

_started = False


def start_scheduler():
    global _started
    if _started or not config.ENABLE_SCHEDULER:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    from .automation import run_daily
    from .database import SessionLocal

    def job():
        db = SessionLocal()
        try:
            run_daily(db)
        finally:
            db.close()

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(job, "cron", hour=7, minute=0, id="daily_reorder")
    sched.start()
    _started = True
