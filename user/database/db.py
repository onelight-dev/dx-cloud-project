from contextlib import contextmanager
import atexit
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=int(os.getenv("DB_POOL_MIN", 1)),
    maxconn=int(os.getenv("DB_POOL_MAX", 10)),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)

atexit.register(_pool.closeall)


class _DictConnWrapper:
    """psycopg2 커넥션을 감싸 cursor()가 항상 RealDictCursor를 반환하게 함."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        kwargs.setdefault("cursor_factory", RealDictCursor)
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def get_db():
    conn = _pool.getconn()
    wrapped = _DictConnWrapper(conn)
    try:
        yield wrapped
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
