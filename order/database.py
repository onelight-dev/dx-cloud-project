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


class Database:
    def get_connection(self):
        """트랜잭션을 위해 직접 커넥션을 반환합니다."""
        return _pool.getconn()

    def release_connection(self, conn):
        _pool.putconn(conn)

    def insert_user(self, cognito_sub, email, name):
        query = """
            INSERT INTO users (id, cognito_sub, email, name, role, status, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, 'USER', 'ACTIVE', NOW(), NOW())
            RETURNING id
        """
        result = self.execute_commit_returning(query, (cognito_sub, email, name))
        return result['id']

    def execute_query_one(self, query, params=None):
        conn = _pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchone()
        finally:
            _pool.putconn(conn)

    def execute_query(self, query, params=None):
        conn = _pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            _pool.putconn(conn)

    def execute_commit_returning(self, query, params=None):
        conn = _pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()
                return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            _pool.putconn(conn)

    def get_or_create_wishlist(self, user_id):
        query = "SELECT id FROM wishlists WHERE user_id = %s"
        wishlist = self.execute_query_one(query, (user_id,))
        if not wishlist:
            create_query = "INSERT INTO wishlists (id, user_id) VALUES (gen_random_uuid(), %s) RETURNING id"
            wishlist = self.execute_commit_returning(create_query, (user_id,))
        return wishlist

    def get_or_create_cart(self, user_id):
        query = "SELECT id FROM carts WHERE user_id = %s"
        cart = self.execute_query_one(query, (user_id,))
        if not cart:
            create_query = "INSERT INTO carts (id, user_id) VALUES (gen_random_uuid(), %s) RETURNING id"
            cart = self.execute_commit_returning(create_query, (user_id,))
        return cart

    def execute_transaction(self, queries_with_params):
        conn = _pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                results = []
                for query, params in queries_with_params:
                    cur.execute(query, params)
                    if "RETURNING" in query.upper():
                        results.append(cur.fetchone())
                conn.commit()
                return results
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            _pool.putconn(conn)
