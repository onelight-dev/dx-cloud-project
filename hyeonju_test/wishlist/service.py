from decimal import Decimal
from uuid import uuid4

from psycopg.rows import dict_row

from database.db import get_connection
from users.service import ensure_test_user

print("### DB WISHLIST SERVICE LOADED ###")


def _to_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def ensure_test_wishlist():
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id
                FROM wishlists
                WHERE user_id = %s
                """,
                (user["id"],),
            )
            wishlist = cur.fetchone()

            if wishlist:
                print("### TEST WISHLIST EXISTS ###", wishlist["id"])
                return wishlist

            wishlist_id = str(uuid4())
            cur.execute(
                """
                INSERT INTO wishlists (id, user_id)
                VALUES (%s, %s)
                RETURNING id, user_id
                """,
                (wishlist_id, user["id"]),
            )
            wishlist = cur.fetchone()
            conn.commit()
            print("### TEST WISHLIST CREATED + COMMIT ###", wishlist["id"])
            return wishlist


def get_valid_product_sku(product_id, sku_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    p.id AS product_id,
                    p.name AS product_name,
                    p.slug AS product_slug,
                    p.base_price,
                    p.discount_price,
                    p.is_active,
                    p.is_deleted,
                    ps.id AS sku_id,
                    ps.sku_code,
                    ps.price_override,
                    COALESCE(ps.price_override, p.discount_price, p.base_price) AS unit_price
                FROM products p
                INNER JOIN product_skus ps
                    ON ps.product_id = p.id
                WHERE p.id = %s
                  AND ps.id = %s
                  AND p.is_active = TRUE
                  AND p.is_deleted = FALSE
                """,
                (product_id, sku_id),
            )
            return cur.fetchone()


def get_option_summary(sku_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    STRING_AGG(
                        pog.name || ':' || pov.value,
                        ' / ' ORDER BY pog.sort_order, pov.sort_order
                    ) AS option_summary
                FROM sku_option_values sov
                INNER JOIN product_option_values pov
                    ON pov.id = sov.option_value_id
                INNER JOIN product_option_groups pog
                    ON pog.id = pov.group_id
                WHERE sov.sku_id = %s
                GROUP BY sov.sku_id
                """,
                (sku_id,),
            )
            row = cur.fetchone()
            return row["option_summary"] if row and row["option_summary"] else ""


def get_thumbnail_url(product_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT image_url
                FROM product_images
                WHERE product_id = %s
                ORDER BY is_thumbnail DESC, sort_order ASC, id ASC
                LIMIT 1
                """,
                (product_id,),
            )
            row = cur.fetchone()
            return row["image_url"] if row else None


def get_my_wishlist():
    wishlist = ensure_test_wishlist()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    wi.id AS item_id,
                    wi.product_id,
                    p.name AS product_name,
                    p.slug AS product_slug,
                    wi.sku_id,
                    ps.sku_code,
                    wi.quantity,
                    COALESCE(ps.price_override, p.discount_price, p.base_price) AS unit_price
                FROM wishlist_items wi
                INNER JOIN products p
                    ON p.id = wi.product_id
                INNER JOIN product_skus ps
                    ON ps.id = wi.sku_id
                WHERE wi.wishlist_id = %s
                ORDER BY wi.id ASC
                """,
                (wishlist["id"],),
            )
            rows = cur.fetchall()

    items = []
    total_quantity = 0
    total_amount = Decimal("0")

    for row in rows:
        line_amount = row["unit_price"] * row["quantity"]

        items.append(
            {
                "item_id": row["item_id"],
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "product_slug": row["product_slug"],
                "sku_id": row["sku_id"],
                "sku_code": row["sku_code"],
                "option_summary": get_option_summary(row["sku_id"]),
                "thumbnail_url": get_thumbnail_url(row["product_id"]),
                "quantity": row["quantity"],
                "unit_price": _to_number(row["unit_price"]),
                "line_amount": _to_number(line_amount),
            }
        )
        total_quantity += row["quantity"]
        total_amount += line_amount

    result = {
        "wishlist_id": wishlist["id"],
        "total_quantity": total_quantity,
        "total_amount": _to_number(total_amount),
        "items": items,
    }
    print("### GET WISHLIST ###", result)
    return result


def add_wishlist_item(product_id, sku_id, quantity):
    wishlist = ensure_test_wishlist()

    product_sku = get_valid_product_sku(product_id, sku_id)
    if not product_sku:
        print("### PRODUCT/SKU NOT FOUND FOR WISHLIST ###", {
            "product_id": product_id,
            "sku_id": sku_id,
        })
        return {
            "error": "유효하지 않은 product_id 또는 sku_id입니다.",
            "product_id": product_id,
            "sku_id": sku_id,
        }

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### ADD WISHLIST ITEM INPUT ###", {
                "wishlist_id": wishlist["id"],
                "product_id": product_id,
                "sku_id": sku_id,
                "quantity": quantity,
            })

            cur.execute(
                """
                SELECT id, quantity
                FROM wishlist_items
                WHERE wishlist_id = %s AND sku_id = %s
                """,
                (wishlist["id"], sku_id),
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    """
                    UPDATE wishlist_items
                    SET quantity = quantity + %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (quantity, existing["id"]),
                )
                updated = cur.fetchone()
                print("### WISHLIST ITEM UPDATED ###", updated)
            else:
                cur.execute(
                    """
                    INSERT INTO wishlist_items (id, wishlist_id, product_id, sku_id, quantity)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (str(uuid4()), wishlist["id"], product_id, sku_id, quantity),
                )
                inserted = cur.fetchone()
                print("### WISHLIST ITEM INSERTED ###", inserted)

            conn.commit()
            print("### ADD WISHLIST ITEM COMMIT ###", {"wishlist_id": wishlist["id"], "sku_id": sku_id})

    return {
        "message": "위시리스트에 상품이 추가되었습니다.",
        "wishlist": get_my_wishlist(),
    }


def update_wishlist_item(item_id, quantity):
    wishlist = ensure_test_wishlist()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### UPDATE WISHLIST ITEM INPUT ###", {
                "item_id": item_id,
                "quantity": quantity,
                "wishlist_id": wishlist["id"],
            })

            cur.execute(
                """
                UPDATE wishlist_items
                SET quantity = %s
                WHERE id = %s AND wishlist_id = %s
                RETURNING id
                """,
                (quantity, item_id, wishlist["id"]),
            )
            updated = cur.fetchone()
            conn.commit()

            print("### UPDATE WISHLIST ITEM COMMIT ###", updated)

    if not updated:
        return {"error": "위시리스트 아이템을 찾을 수 없습니다."}

    return {
        "message": "위시리스트 아이템이 수정되었습니다.",
        "wishlist": get_my_wishlist(),
    }


def delete_wishlist_item(item_id):
    wishlist = ensure_test_wishlist()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### DELETE WISHLIST ITEM INPUT ###", {
                "item_id": item_id,
                "wishlist_id": wishlist["id"],
            })

            cur.execute(
                """
                DELETE FROM wishlist_items
                WHERE id = %s AND wishlist_id = %s
                RETURNING id
                """,
                (item_id, wishlist["id"]),
            )
            deleted = cur.fetchone()
            conn.commit()

            print("### DELETE WISHLIST ITEM COMMIT ###", deleted)

    if not deleted:
        return {"error": "위시리스트 아이템을 찾을 수 없습니다."}

    return {
        "message": "아이템이 위시리스트에서 삭제되었습니다.",
        "wishlist": get_my_wishlist(),
    }


def clear_wishlist():
    wishlist = ensure_test_wishlist()

    with get_connection() as conn:
        with conn.cursor() as cur:
            print("### CLEAR WISHLIST INPUT ###", {"wishlist_id": wishlist["id"]})

            cur.execute(
                """
                DELETE FROM wishlist_items
                WHERE wishlist_id = %s
                """,
                (wishlist["id"],),
            )
            conn.commit()

            print("### CLEAR WISHLIST COMMIT ###", {"wishlist_id": wishlist["id"]})

    return {"message": "위시리스트가 비워졌습니다."}