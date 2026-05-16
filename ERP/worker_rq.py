from rq import Connection, Worker

from app.tasks.rq_queue import get_redis_connection


if __name__ == "__main__":
    redis_conn = get_redis_connection()
    with Connection(redis_conn):
        worker = Worker(["erp-default", "erp-heavy"])
        worker.work(with_scheduler=True)
