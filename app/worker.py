"""Punto de entrada del worker RQ.

Se ejecuta con: python -m app.worker
Procesa la cola de a un job (el equipo NMR es un recurso físico único).
"""

import redis
from rq import Queue, Worker

from . import config


def main():
    conn = redis.Redis.from_url(config.REDIS_URL)
    queue = Queue(config.QUEUE_NAME, connection=conn)
    worker = Worker([queue], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
