from database.db import get_db


def list_wishlist_items(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, product_id, created_at
                FROM wishlists
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return cur.fetchall()


def add_wishlist_item(user_id: str, product_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, product_id, created_at FROM wishlists WHERE user_id = %s AND product_id = %s",
                (user_id, product_id),
            )
            existing = cur.fetchone()
            if existing:
                return existing
            cur.execute(
                "INSERT INTO wishlists (user_id, product_id) VALUES (%s, %s) RETURNING id, user_id, product_id, created_at",
                (user_id, product_id),
            )
            return cur.fetchone()


def delete_wishlist_item(user_id: str, wishlist_item_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM wishlists WHERE user_id = %s AND id = %s RETURNING id",
                (user_id, wishlist_item_id),
            )
            return cur.fetchone() is not None
