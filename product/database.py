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
    """커넥션 풀에서 커넥션을 대여하는 컨텍스트 매니저.

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(...)
        conn.commit()
    """
    if _pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았습니다. init_pool()을 먼저 호출하세요.")

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
    """커넥션과 RealDictCursor를 함께 대여하는 편의 컨텍스트 매니저.

    with get_cursor(commit=True) as cur:
        cur.execute("INSERT ...")
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
