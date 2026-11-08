"""Worker role: executes queued evaluation jobs. With CQA_REDIS_URL set it blocks on a Redis
Stream (`cqa:jobs`, consumer group `eval`); otherwise it polls the jobs table every 2 s.
The API enqueues by inserting a Job row and, when Redis is configured, XADD-ing its id."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select

from . import db
from .api.app import run_job
from .config import settings

log = logging.getLogger("cqa.worker")


def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("worker started (queue=%s)", "redis" if settings.redis_url else "db-poll")
    if settings.redis_url:
        import redis
        r = redis.Redis.from_url(settings.redis_url)
        try:
            r.xgroup_create("cqa:jobs", "eval", id="0", mkstream=True)
        except redis.ResponseError:
            pass
        consumer = f"w-{int(time.time())}"
        while True:
            msgs = r.xreadgroup("eval", consumer, {"cqa:jobs": ">"}, count=1, block=5000)
            for _stream, entries in msgs or []:
                for mid, fields in entries:
                    jid = int(fields[b"job_id"])
                    run_job(jid)
                    r.xack("cqa:jobs", "eval", mid)
    else:
        while True:
            with db.session() as s:
                job = s.scalar(select(db.Job).where(db.Job.status == "queued").order_by(db.Job.id))
                jid = job.id if job else None
                if job:
                    job.status = "running"; s.commit()
            if jid:
                run_job(jid)
            else:
                time.sleep(2)


if __name__ == "__main__":
    main()
