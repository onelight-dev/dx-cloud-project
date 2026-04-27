from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from config.db import DB_CONFIG, DB_POOL_MIN, DB_POOL_MAX

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = pool.ThreadedConnectionPool(DB_POOL_MIN, DB_POOL_MAX, **DB_CONFIG)


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_db():
    if _pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았습니다.")
    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(commit: bool = False):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
