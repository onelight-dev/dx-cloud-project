from decimal import Decimal
from uuid import uuid4

from psycopg.rows import dict_row

from database.db import get_connection
from users.service import ensure_test_user

print("### DB CART SERVICE LOADED ###")


def _to_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def ensure_test_cart():
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id
                FROM carts
                WHERE user_id = %s
                """,
                (user["id"],),
            )
            cart = cur.fetchone()

            if cart:
                print("### TEST CART EXISTS ###", cart["id"])
                return cart

            cart_id = str(uuid4())
            cur.execute(
                """
                INSERT INTO carts (id, user_id)
                VALUES (%s, %s)
                RETURNING id, user_id
                """,
                (cart_id, user["id"]),
            )
            cart = cur.fetchone()
            conn.commit()
            print("### TEST CART CREATED + COMMIT ###", cart["id"])
            return cart


def get_valid_product_sku(product_id, sku_id):
    """
    등록된 실제 상품 + 실제 SKU만 허용
    """
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
    """
    옵션 테이블이 비어 있어도 장바구니는 동작하게 처리
    """
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
    """
    이미지가 없어도 장바구니는 동작하게 처리
    """
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


def get_my_cart():
    cart = ensure_test_cart()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    ci.id AS item_id,
                    ci.product_id,
                    p.name AS product_name,
                    p.slug AS product_slug,
                    ci.sku_id,
                    ps.sku_code,
                    ci.quantity,
                    COALESCE(ps.price_override, p.discount_price, p.base_price) AS unit_price
                FROM cart_items ci
                INNER JOIN products p
                    ON p.id = ci.product_id
                INNER JOIN product_skus ps
                    ON ps.id = ci.sku_id
                WHERE ci.cart_id = %s
                ORDER BY ci.id ASC
                """,
                (cart["id"],),
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
        "cart_id": cart["id"],
        "total_quantity": total_quantity,
        "total_amount": _to_number(total_amount),
        "items": items,
    }
    print("### GET CART ###", result)
    return result


def add_cart_item(product_id, sku_id, quantity):
    cart = ensure_test_cart()

    product_sku = get_valid_product_sku(product_id, sku_id)
    if not product_sku:
        print("### PRODUCT/SKU NOT FOUND ###", {
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
            print("### ADD CART ITEM INPUT ###", {
                "cart_id": cart["id"],
                "product_id": product_id,
                "sku_id": sku_id,
                "quantity": quantity,
            })

            cur.execute(
                """
                SELECT id, quantity
                FROM cart_items
                WHERE cart_id = %s AND sku_id = %s
                """,
                (cart["id"], sku_id),
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    """
                    UPDATE cart_items
                    SET quantity = quantity + %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (quantity, existing["id"]),
                )
                updated = cur.fetchone()
                print("### CART ITEM UPDATED ###", updated)
            else:
                cur.execute(
                    """
                    INSERT INTO cart_items (id, cart_id, product_id, sku_id, quantity)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (str(uuid4()), cart["id"], product_id, sku_id, quantity),
                )
                inserted = cur.fetchone()
                print("### CART ITEM INSERTED ###", inserted)

            conn.commit()
            print("### ADD CART ITEM COMMIT ###", {"cart_id": cart["id"], "sku_id": sku_id})

    return {
        "message": "장바구니에 상품이 추가되었습니다.",
        "cart": get_my_cart(),
    }


def update_cart_item(item_id, quantity):
    cart = ensure_test_cart()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### UPDATE CART ITEM INPUT ###", {
                "item_id": item_id,
                "quantity": quantity,
                "cart_id": cart["id"],
            })

            cur.execute(
                """
                UPDATE cart_items
                SET quantity = %s
                WHERE id = %s AND cart_id = %s
                RETURNING id
                """,
                (quantity, item_id, cart["id"]),
            )
            updated = cur.fetchone()
            conn.commit()

            print("### UPDATE CART ITEM COMMIT ###", updated)

    if not updated:
        return {"error": "장바구니 아이템을 찾을 수 없습니다."}

    return {
        "message": "장바구니 아이템이 수정되었습니다.",
        "cart": get_my_cart(),
    }


def delete_cart_item(item_id):
    cart = ensure_test_cart()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### DELETE CART ITEM INPUT ###", {
                "item_id": item_id,
                "cart_id": cart["id"],
            })

            cur.execute(
                """
                DELETE FROM cart_items
                WHERE id = %s AND cart_id = %s
                RETURNING id
                """,
                (item_id, cart["id"]),
            )
            deleted = cur.fetchone()
            conn.commit()

            print("### DELETE CART ITEM COMMIT ###", deleted)

    if not deleted:
        return {"error": "장바구니 아이템을 찾을 수 없습니다."}

    return {
        "message": "아이템이 장바구니에서 삭제되었습니다.",
        "cart": get_my_cart(),
    }


def clear_cart():
    cart = ensure_test_cart()

    with get_connection() as conn:
        with conn.cursor() as cur:
            print("### CLEAR CART INPUT ###", {"cart_id": cart["id"]})

            cur.execute(
                """
                DELETE FROM cart_items
                WHERE cart_id = %s
                """,
                (cart["id"],),
            )
            conn.commit()

            print("### CLEAR CART COMMIT ###", {"cart_id": cart["id"]})

    return {"message": "장바구니가 비워졌습니다."}