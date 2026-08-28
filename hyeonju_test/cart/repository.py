from uuid import uuid4

from psycopg.rows import dict_row

from database.db import get_connection


def get_cart_by_user_id(user_id: str) -> dict | None:
    query = """
        SELECT id, user_id
        FROM carts
        WHERE user_id = %s
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (user_id,))
        return cur.fetchone()


def create_cart_for_user(user_id: str) -> dict:
    query = """
        INSERT INTO carts (id, user_id)
        VALUES (%s, %s)
        RETURNING id, user_id
    """
    cart_id = str(uuid4())
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (cart_id, user_id))
        return cur.fetchone()


def get_cart_detail_by_user_id(user_id: str) -> dict:
    cart_query = """
        SELECT id
        FROM carts
        WHERE user_id = %s
    """

    items_query = """
        SELECT
            ci.id AS item_id,
            ci.product_id,
            p.name AS product_name,
            p.slug AS product_slug,
            ci.sku_id,
            ps.sku_code,
            ci.quantity,
            COALESCE(ps.price_override, p.discount_price, p.base_price) AS unit_price,
            pi.image_url AS thumbnail_url,
            COALESCE(opt.option_summary, '') AS option_summary
        FROM cart_items ci
        INNER JOIN carts c
            ON c.id = ci.cart_id
        INNER JOIN products p
            ON p.id = ci.product_id
        INNER JOIN product_skus ps
            ON ps.id = ci.sku_id
        LEFT JOIN product_images pi
            ON pi.product_id = p.id
           AND pi.is_thumbnail = TRUE
        LEFT JOIN (
            SELECT
                sov.sku_id,
                STRING_AGG(pog.name || ':' || pov.value, ' / ' ORDER BY pog.sort_order, pov.sort_order) AS option_summary
            FROM sku_option_values sov
            INNER JOIN product_option_values pov
                ON pov.id = sov.option_value_id
            INNER JOIN product_option_groups pog
                ON pog.id = pov.group_id
            GROUP BY sov.sku_id
        ) opt
            ON opt.sku_id = ci.sku_id
        WHERE c.user_id = %s
        ORDER BY ci.id ASC
    """

    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(cart_query, (user_id,))
        cart = cur.fetchone()

        if not cart:
            return {"cart_id": None, "items": []}

        cur.execute(items_query, (user_id,))
        items = cur.fetchall()
        return {"cart_id": cart["id"], "items": items}


def get_product_and_sku_snapshot(product_id: str, sku_id: str) -> dict | None:
    query = """
        SELECT
            p.id AS product_id,
            ps.id AS sku_id,
            p.name,
            p.slug,
            ps.sku_code,
            COALESCE(ps.price_override, p.discount_price, p.base_price) AS unit_price
        FROM products p
        INNER JOIN product_skus ps
            ON ps.product_id = p.id
        WHERE p.id = %s
          AND ps.id = %s
          AND p.is_active = TRUE
          AND p.is_deleted = FALSE
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (product_id, sku_id))
        return cur.fetchone()


def get_cart_item_by_cart_id_and_sku_id(cart_id: str, sku_id: str) -> dict | None:
    query = """
        SELECT id, cart_id, product_id, sku_id, quantity
        FROM cart_items
        WHERE cart_id = %s
          AND sku_id = %s
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (cart_id, sku_id))
        return cur.fetchone()


def upsert_cart_item_quantity(
    item_id: str | None,
    cart_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
    quantity: int | None = None,
) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        if item_id:
            query = """
                UPDATE cart_items
                SET quantity = %s
                WHERE id = %s
            """
            cur.execute(query, (quantity, item_id))
        else:
            query = """
                INSERT INTO cart_items (id, cart_id, product_id, sku_id, quantity)
                VALUES (%s, %s, %s, %s, %s)
            """
            cur.execute(query, (str(uuid4()), cart_id, product_id, sku_id, quantity))


def find_cart_item_by_id_for_user(item_id: str, user_id: str) -> dict | None:
    query = """
        SELECT
            ci.id,
            ci.cart_id,
            ci.product_id,
            ci.sku_id,
            ci.quantity
        FROM cart_items ci
        INNER JOIN carts c
            ON c.id = ci.cart_id
        WHERE ci.id = %s
          AND c.user_id = %s
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (item_id, user_id))
        return cur.fetchone()


def set_cart_item_quantity(item_id: str, quantity: int) -> None:
    query = """
        UPDATE cart_items
        SET quantity = %s
        WHERE id = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (quantity, item_id))


def update_cart_item_sku_and_quantity(item_id: str, sku_id: str, quantity: int) -> None:
    query = """
        UPDATE cart_items
        SET sku_id = %s,
            quantity = %s
        WHERE id = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (sku_id, quantity, item_id))


def delete_cart_item_by_id(item_id: str) -> None:
    query = """
        DELETE FROM cart_items
        WHERE id = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (item_id,))


def clear_cart_items_by_user_id(user_id: str) -> None:
    query = """
        DELETE FROM cart_items ci
        USING carts c
        WHERE ci.cart_id = c.id
          AND c.user_id = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (user_id,))
