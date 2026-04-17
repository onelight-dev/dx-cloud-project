from database.db import get_db


def get_or_create_cart(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, created_at, updated_at FROM carts WHERE user_id = %s", (user_id,))
            cart = cur.fetchone()
            if cart:
                return cart
            cur.execute(
                "INSERT INTO carts (user_id) VALUES (%s) RETURNING id, user_id, created_at, updated_at",
                (user_id,),
            )
            return cur.fetchone()


def get_cart_detail(cart_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, created_at, updated_at FROM carts WHERE id = %s", (cart_id,))
            cart = cur.fetchone()
            cur.execute(
                """
                SELECT id, cart_id, product_id, sku_id, quantity, created_at, updated_at
                FROM cart_items
                WHERE cart_id = %s
                ORDER BY created_at DESC
                """,
                (cart_id,),
            )
            items = cur.fetchall()
            cart["items"] = items
            return cart


def add_cart_item(user_id: str, payload: dict):
    quantity = int(payload["quantity"])
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    cart = get_or_create_cart(user_id)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, quantity FROM cart_items WHERE cart_id = %s AND product_id = %s AND COALESCE(sku_id::text, '') = COALESCE(%s, '')",
                (cart["id"], payload["product_id"], payload.get("sku_id")),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE cart_items
                    SET quantity = quantity + %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, cart_id, product_id, sku_id, quantity, created_at, updated_at
                    """,
                    (quantity, existing["id"]),
                )
                return cur.fetchone()

            cur.execute(
                """
                INSERT INTO cart_items (cart_id, product_id, sku_id, quantity)
                VALUES (%s, %s, %s, %s)
                RETURNING id, cart_id, product_id, sku_id, quantity, created_at, updated_at
                """,
                (cart["id"], payload["product_id"], payload.get("sku_id"), quantity),
            )
            return cur.fetchone()


def update_cart_item(user_id: str, item_id: str, quantity: int):
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cart_items ci
                SET quantity = %s, updated_at = NOW()
                FROM carts c
                WHERE ci.cart_id = c.id AND c.user_id = %s AND ci.id = %s
                RETURNING ci.id, ci.cart_id, ci.product_id, ci.sku_id, ci.quantity, ci.created_at, ci.updated_at
                """,
                (quantity, user_id, item_id),
            )
            return cur.fetchone()


def delete_cart_item(user_id: str, item_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM cart_items ci
                USING carts c
                WHERE ci.cart_id = c.id AND c.user_id = %s AND ci.id = %s
                RETURNING ci.id
                """,
                (user_id, item_id),
            )
            return cur.fetchone() is not None


def clear_cart(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE user_id = %s)",
                (user_id,),
            )
