import random
import time
from dataclasses import dataclass

from sqlalchemy import and_, or_, select

from .db import jobs, new_id


@dataclass(frozen=True)
class JobLease:
    job_id: str
    stage: str
    payload: dict
    fence: int
    worker: str


class Queue:
    def __init__(self, repo, clock=time.time, lease_seconds=600, max_attempts=3):
        self.repo, self.clock = repo, clock
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts

    def enqueue(self, stage, key, payload, conn=None, *, retry_failed=False):
        if conn is None:
            with self.repo.write() as connection:
                return self.enqueue(stage, key, payload, connection, retry_failed=retry_failed)
        # Upsert makes concurrent scanners harmless on both supported backends.
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = pg_insert if self.repo.postgres else sqlite_insert
        conn.execute(insert(jobs).values(job_id=new_id(), stage=stage, key=key, payload=payload, state="queued",
                     attempt=0, fence=0, next_attempt=0, created_at=self.clock())
                     .on_conflict_do_nothing(index_elements=["stage", "key"]))
        if retry_failed:
            conn.execute(jobs.update().where(and_(jobs.c.stage == stage, jobs.c.key == key, jobs.c.state == "failed"))
                         .values(state="queued", attempt=0, next_attempt=0, lease_until=None,
                                 worker=None, error=None, result=None))
        return self.repo.one(jobs, and_(jobs.c.stage == stage, jobs.c.key == key), conn)["job_id"]

    def claim_job(self, worker_id, stages):
        now = self.clock()
        with self.repo.write() as conn:
            expired = and_(jobs.c.state == "running", jobs.c.lease_until <= now)
            conn.execute(jobs.update().where(and_(expired, jobs.c.attempt >= self.max_attempts))
                         .values(state="failed", error="Lease expired; attempts exhausted"))
            eligible = or_(and_(jobs.c.state.in_(["queued", "retry_wait"]), jobs.c.next_attempt <= now), expired)
            query = select(jobs).where(and_(eligible, jobs.c.stage.in_(stages), jobs.c.attempt < self.max_attempts))
            query = query.order_by(jobs.c.created_at, jobs.c.job_id).limit(1)
            if self.repo.postgres:
                query = query.with_for_update(skip_locked=True)
            row = conn.execute(query).mappings().first()
            if not row:
                return None
            fence = row["fence"] + 1
            conn.execute(jobs.update().where(jobs.c.job_id == row["job_id"]).values(state="running", worker=worker_id,
                         fence=fence, attempt=row["attempt"] + 1, lease_until=now + self.lease_seconds))
            return JobLease(row["job_id"], row["stage"], row["payload"], fence, worker_id)

    def valid_condition(self, lease):
        return and_(jobs.c.job_id == lease.job_id, jobs.c.fence == lease.fence, jobs.c.worker == lease.worker,
                    jobs.c.state == "running", jobs.c.lease_until > self.clock())

    def complete_job(self, lease, result, publisher=None):
        with self.repo.write() as conn:
            claimed = conn.execute(jobs.update().where(self.valid_condition(lease)).values(state="succeeded", result=result))
            if claimed.rowcount != 1:
                return False
            if publisher:
                publisher(conn)
            return True

    def heartbeat(self, lease):
        with self.repo.write() as conn:
            return conn.execute(jobs.update().where(self.valid_condition(lease))
                       .values(lease_until=self.clock() + self.lease_seconds)).rowcount == 1

    def fail_job(self, lease, error, permanent=False):
        with self.repo.write() as conn:
            row = self.repo.one(jobs, jobs.c.job_id == lease.job_id, conn)
            terminal = permanent or row["attempt"] >= self.max_attempts
            return conn.execute(jobs.update().where(self.valid_condition(lease)).values(
                state="failed" if terminal else "retry_wait", error=str(error)[:2000], lease_until=None,
                next_attempt=self.clock() + min(300, 2 ** row["attempt"] + random.random()))).rowcount == 1

    def get(self, job_id):
        return self.repo.one(jobs, jobs.c.job_id == str(job_id))
