from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from flask import current_app


def get_dsn() -> str:
    return (
        f"host={current_app.config['DB_HOST']} "
        f"port={current_app.config['DB_PORT']} "
        f"dbname={current_app.config['DB_NAME']} "
        f"user={current_app.config['DB_USER']} "
        f"password={current_app.config['DB_PASSWORD']}"
    )


@contextmanager
def get_db():
    conn = psycopg.connect(get_dsn(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
