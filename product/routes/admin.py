from flask import Blueprint, render_template, jsonify, request
from database import get_cursor
import psycopg2

bp = Blueprint("admin", __name__, url_prefix="/admin",
               template_folder="../templates")


# ─────────────────────────────────────────────
# HTML 페이지 라우트
# ─────────────────────────────────────────────

@bp.get("/")
@bp.get("")
def dashboard():
    return render_template("admin/users.html")


@bp.get("/users")
def users_page():
    return render_template("admin/users.html")


@bp.get("/categories")
def categories_page():
    return render_template("admin/categories.html")


@bp.get("/products")
def products_page():
    return render_template("admin/products.html")


@bp.get("/orders")
def orders_page():
    return render_template("admin/orders.html")


# ─────────────────────────────────────────────
# 사용자 API  (GET 목록 / GET 단건 / PUT 수정)
# ─────────────────────────────────────────────

@bp.get("/api/users")
def list_users():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()

    conditions = []
    params: list = []

    if search:
        conditions.append("(email ILIKE %s OR name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM users {where}", params)
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT id, cognito_sub, email, name, phone, role, status,
                   created_at, updated_at, withdrawn_at
            FROM users
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    items = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        items.append(d)

    return jsonify({
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
        },
    })


@bp.get("/api/users/<uuid:user_id>")
def get_user(user_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, cognito_sub, email, name, phone, role, status,
                   created_at, updated_at, withdrawn_at
            FROM users WHERE id = %s
            """,
            (str(user_id),),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404

    d = dict(row)
    d["id"] = str(d["id"])
    return jsonify({"data": d})


@bp.put("/api/users/<uuid:user_id>")
def update_user(user_id):
    body = request.get_json(silent=True) or {}

    fields: dict = {}
    if "name"   in body: fields["name"]   = body["name"].strip()
    if "phone"  in body: fields["phone"]  = body["phone"] or None
    if "role"   in body: fields["role"]   = body["role"]
    if "status" in body: fields["status"] = body["status"]

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [str(user_id)]

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"""
                UPDATE users SET {set_clause}
                WHERE id = %s
                RETURNING id, email, name, phone, role, status, updated_at
                """,
                values,
            )
            row = cur.fetchone()
    except psycopg2.errors.InvalidTextRepresentation:
        return jsonify({"error": "유효하지 않은 값입니다."}), 400

    if not row:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404

    d = dict(row)
    d["id"] = str(d["id"])
    return jsonify({"data": d})


# ─────────────────────────────────────────────
# 주문 API  (GET 목록 / GET 단건)
# ─────────────────────────────────────────────

@bp.get("/api/orders")
def list_orders():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    status = request.args.get("status", "").strip()

    conditions = []
    params: list = []

    if status:
        conditions.append("o.status = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS total FROM orders o {where}", params
        )
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT o.id, o.order_number, o.status,
                   o.total_amount, o.discount_amount, o.shipping_fee, o.final_amount,
                   o.payment_method, o.paid_at,
                   o.recipient, o.phone, o.zip_code, o.address1, o.address2,
                   o.created_at, o.updated_at,
                   u.email AS user_email, u.name AS user_name
            FROM orders o
            LEFT JOIN users u ON u.id = o.user_id
            {where}
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    items = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        items.append(d)

    return jsonify({
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
        },
    })


@bp.get("/api/orders/<uuid:order_id>")
def get_order(order_id):
    oid = str(order_id)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.order_number, o.status,
                   o.total_amount, o.discount_amount, o.shipping_fee, o.final_amount,
                   o.payment_method, o.payment_key, o.paid_at,
                   o.recipient, o.phone, o.zip_code, o.address1, o.address2,
                   o.user_memo, o.admin_memo, o.created_at, o.updated_at,
                   u.email AS user_email, u.name AS user_name
            FROM orders o
            LEFT JOIN users u ON u.id = o.user_id
            WHERE o.id = %s
            """,
            (oid,),
        )
        order = cur.fetchone()

        if not order:
            return jsonify({"error": "주문을 찾을 수 없습니다."}), 404

        order = dict(order)
        order["id"] = str(order["id"])

        cur.execute(
            """
            SELECT id, product_name, sku_code, option_summary,
                   unit_price, quantity, subtotal
            FROM order_items
            WHERE order_id = %s
            ORDER BY created_at
            """,
            (oid,),
        )
        order["items"] = [
            {**dict(r), "id": str(r["id"])} for r in cur.fetchall()
        ]

    return jsonify({"data": order})
