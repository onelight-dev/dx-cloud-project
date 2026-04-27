from decimal import Decimal
from flask import Blueprint, render_template, jsonify, request
from database import get_cursor
import psycopg2
import uuid as _uuid_mod

bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _val(v):
    if isinstance(v, _uuid_mod.UUID): return str(v)
    if isinstance(v, Decimal): return float(v)
    return v

def _row(r):
    if r is None: return None
    return {k: _val(v) for k, v in dict(r).items()}

def _rows(rs): return [_row(r) for r in rs]

def _pg(page, limit, total):
    return {"total": total, "page": page, "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit)}


# ── HTML Page Routes ───────────────────────────────────────────────────────────

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

@bp.get("/outfits")
def outfits_page():
    return render_template("admin/outfits.html")

@bp.get("/cart")
def cart_page():
    return render_template("admin/cart.html")

@bp.get("/orders")
def orders_page():
    return render_template("admin/orders.html")


# ── Users API ──────────────────────────────────────────────────────────────────

@bp.get("/api/users")
def list_users():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    role   = request.args.get("role", "").strip()
    status = request.args.get("status", "").strip()

    conds, params = [], []
    if search:
        conds.append("(email ILIKE %s OR name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if role:   conds.append("role = %s");   params.append(role)
    if status: conds.append("status = %s"); params.append(status)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM users {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT id, cognito_sub, email, name, phone, role, status, created_at, updated_at "
            f"FROM users {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows), "pagination": _pg(page, limit, total)})


@bp.get("/api/users/<uuid:uid>")
def get_user(uid):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, cognito_sub, email, name, phone, role, status, created_at, updated_at "
            "FROM users WHERE id = %s", (str(uid),)
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.put("/api/users/<uuid:uid>")
def update_user(uid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "name"   in body: fields["name"]   = (body["name"] or "").strip()
    if "phone"  in body: fields["phone"]  = body["phone"] or None
    if "role"   in body: fields["role"]   = body["role"]
    if "status" in body: fields["status"] = body["status"]
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE users SET {set_clause} WHERE id = %s "
                f"RETURNING id, email, name, phone, role, status, updated_at",
                list(fields.values()) + [str(uid)],
            )
            row = cur.fetchone()
    except psycopg2.errors.InvalidTextRepresentation:
        return jsonify({"error": "유효하지 않은 값입니다."}), 400
    if not row: return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


# ── Categories API ─────────────────────────────────────────────────────────────

@bp.get("/api/categories")
def list_categories():
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, slug, parent_id, description, sort_order, is_active, created_at, updated_at "
            "FROM categories ORDER BY sort_order, name"
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows)})


@bp.get("/api/categories/<uuid:cid>")
def get_category(cid):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, slug, parent_id, description, sort_order, is_active, created_at, updated_at "
            "FROM categories WHERE id = %s", (str(cid),)
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.post("/api/categories")
def create_category():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    slug = (body.get("slug") or "").strip()
    if not name or not slug:
        return jsonify({"error": "이름과 slug는 필수입니다."}), 400
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO categories (name, slug, parent_id, description, sort_order, is_active)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id, name, slug, parent_id, description, sort_order, is_active, created_at""",
                (name, slug, body.get("parent_id") or None, body.get("description") or None,
                 int(body.get("sort_order", 0)), bool(body.get("is_active", True))),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/categories/<uuid:cid>")
def update_category(cid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "name"        in body: fields["name"]        = body["name"].strip()
    if "slug"        in body: fields["slug"]        = body["slug"].strip()
    if "parent_id"   in body: fields["parent_id"]   = body["parent_id"] or None
    if "description" in body: fields["description"] = body["description"] or None
    if "sort_order"  in body: fields["sort_order"]  = int(body["sort_order"])
    if "is_active"   in body: fields["is_active"]   = bool(body["is_active"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE categories SET {set_clause} WHERE id = %s "
                f"RETURNING id, name, slug, parent_id, description, sort_order, is_active, updated_at",
                list(fields.values()) + [str(cid)],
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    if not row: return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/categories/<uuid:cid>")
def delete_category(cid):
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM categories WHERE id = %s RETURNING id", (str(cid),))
            row = cur.fetchone()
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "해당 카테고리를 사용하는 상품이 있습니다."}), 409
    if not row: return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


# ── Products API ───────────────────────────────────────────────────────────────

@bp.get("/api/products")
def list_products():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()
    cat_id = request.args.get("category_id", "").strip()

    conds, params = ["p.is_deleted = FALSE"], []
    if search: conds.append("p.name ILIKE %s"); params.append(f"%{search}%")
    if cat_id: conds.append("p.category_id = %s"); params.append(cat_id)
    where = "WHERE " + " AND ".join(conds)

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM products p {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT p.id, p.name, p.slug, p.category_id, c.name AS category_name,
                       p.description, p.base_price, p.discount_price, p.is_active,
                       p.created_at, p.updated_at,
                       (SELECT pi.image_url FROM product_images pi
                        WHERE pi.product_id = p.id AND pi.is_thumbnail = TRUE LIMIT 1) AS thumbnail_url
                FROM products p
                LEFT JOIN categories c ON c.id = p.category_id
                {where} ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows), "pagination": _pg(page, limit, total)})


@bp.get("/api/products/<uuid:pid>")
def get_product(pid):
    pid_s = str(pid)
    with get_cursor() as cur:
        cur.execute(
            """SELECT p.id, p.name, p.slug, p.category_id, c.name AS category_name,
                      p.description, p.base_price, p.discount_price, p.is_active, p.created_at, p.updated_at
               FROM products p LEFT JOIN categories c ON c.id = p.category_id
               WHERE p.id = %s AND p.is_deleted = FALSE""",
            (pid_s,),
        )
        product = cur.fetchone()
        if not product: return jsonify({"error": "상품을 찾을 수 없습니다."}), 404
        product = _row(product)
        cur.execute(
            "SELECT id, image_url, alt_text, sort_order, is_thumbnail, created_at "
            "FROM product_images WHERE product_id = %s ORDER BY sort_order",
            (pid_s,),
        )
        product["images"] = _rows(cur.fetchall())
    return jsonify({"data": product})


@bp.post("/api/products")
def create_product():
    body = request.get_json(silent=True) or {}
    name       = (body.get("name") or "").strip()
    slug       = (body.get("slug") or "").strip()
    cat_id     = body.get("category_id")
    base_price = body.get("base_price")
    if not name or not slug or not cat_id or base_price is None:
        return jsonify({"error": "상품명, slug, 카테고리, 기본가는 필수입니다."}), 400
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO products (name, slug, category_id, description, base_price, discount_price, is_active)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, name, slug, category_id, description, base_price, discount_price, is_active, created_at""",
                (name, slug, cat_id, body.get("description") or None, float(base_price),
                 float(body["discount_price"]) if body.get("discount_price") else None,
                 bool(body.get("is_active", True))),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/products/<uuid:pid>")
def update_product(pid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "name"           in body: fields["name"]           = body["name"].strip()
    if "slug"           in body: fields["slug"]           = body["slug"].strip()
    if "category_id"    in body: fields["category_id"]    = body["category_id"] or None
    if "description"    in body: fields["description"]    = body["description"] or None
    if "base_price"     in body: fields["base_price"]     = float(body["base_price"])
    if "discount_price" in body:
        fields["discount_price"] = float(body["discount_price"]) if body["discount_price"] else None
    if "is_active"      in body: fields["is_active"]      = bool(body["is_active"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE products SET {set_clause} WHERE id = %s AND is_deleted = FALSE "
                f"RETURNING id, name, slug, category_id, description, base_price, discount_price, is_active, updated_at",
                list(fields.values()) + [str(pid)],
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    if not row: return jsonify({"error": "상품을 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/products/<uuid:pid>")
def delete_product(pid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE products SET is_deleted = TRUE, is_active = FALSE "
            "WHERE id = %s AND is_deleted = FALSE RETURNING id",
            (str(pid),),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "상품을 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


# ── Product Images API ─────────────────────────────────────────────────────────

@bp.post("/api/products/<uuid:pid>/images")
def upload_product_image(pid):
    pid_s = str(pid)
    file = request.files.get("image")
    if not file: return jsonify({"error": "이미지 파일이 없습니다."}), 400
    alt_text     = request.form.get("alt_text", "")
    sort_order   = int(request.form.get("sort_order", 0))
    is_thumbnail = request.form.get("is_thumbnail", "false").lower() == "true"
    try:
        from services.s3_service import upload_image
        image_url = upload_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    with get_cursor(commit=True) as cur:
        if is_thumbnail:
            cur.execute("UPDATE product_images SET is_thumbnail = FALSE WHERE product_id = %s", (pid_s,))
        cur.execute(
            """INSERT INTO product_images (product_id, image_url, alt_text, sort_order, is_thumbnail)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, product_id, image_url, alt_text, sort_order, is_thumbnail, created_at""",
            (pid_s, image_url, alt_text or None, sort_order, is_thumbnail),
        )
        row = cur.fetchone()
    return jsonify({"data": _row(row)}), 201


@bp.delete("/api/products/<uuid:pid>/images/<uuid:iid>")
def delete_product_image(pid, iid):
    with get_cursor() as cur:
        cur.execute(
            "SELECT image_url FROM product_images WHERE id = %s AND product_id = %s",
            (str(iid), str(pid)),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404
    try:
        from services.s3_service import delete_image
        delete_image(row["image_url"])
    except Exception:
        pass
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM product_images WHERE id = %s", (str(iid),))
    return jsonify({"message": "삭제되었습니다."})


# ── Product Options API ────────────────────────────────────────────────────────

@bp.get("/api/products/<uuid:pid>/options")
def get_product_options(pid):
    pid_s = str(pid)
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, sort_order FROM product_option_groups WHERE product_id = %s ORDER BY sort_order",
            (pid_s,),
        )
        groups = _rows(cur.fetchall())
        for g in groups:
            cur.execute(
                "SELECT id, value, sort_order FROM product_option_values WHERE group_id = %s ORDER BY sort_order",
                (g["id"],),
            )
            g["values"] = _rows(cur.fetchall())
        cur.execute(
            "SELECT id, sku_code, price_override FROM product_skus WHERE product_id = %s ORDER BY sku_code",
            (pid_s,),
        )
        skus = _rows(cur.fetchall())
        for s in skus:
            cur.execute(
                """SELECT pov.id, pov.value, pog.id AS group_id, pog.name AS group_name
                   FROM sku_option_values sov
                   JOIN product_option_values pov ON pov.id = sov.option_value_id
                   JOIN product_option_groups pog ON pog.id = pov.group_id
                   WHERE sov.sku_id = %s""",
                (s["id"],),
            )
            s["option_values"] = _rows(cur.fetchall())
    return jsonify({"data": {"groups": groups, "skus": skus}})


@bp.post("/api/products/<uuid:pid>/option-groups")
def create_option_group(pid):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name: return jsonify({"error": "그룹명은 필수입니다."}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO product_option_groups (product_id, name, sort_order) VALUES (%s, %s, %s) "
            "RETURNING id, name, sort_order",
            (str(pid), name, int(body.get("sort_order", 0))),
        )
        row = cur.fetchone()
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/products/<uuid:pid>/option-groups/<uuid:gid>")
def update_option_group(pid, gid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "name"       in body: fields["name"]       = body["name"].strip()
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE product_option_groups SET {set_clause} WHERE id = %s AND product_id = %s "
            f"RETURNING id, name, sort_order",
            list(fields.values()) + [str(gid), str(pid)],
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "그룹을 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/products/<uuid:pid>/option-groups/<uuid:gid>")
def delete_option_group(pid, gid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM product_option_groups WHERE id = %s AND product_id = %s RETURNING id",
            (str(gid), str(pid)),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "그룹을 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


@bp.post("/api/products/<uuid:pid>/option-groups/<uuid:gid>/values")
def create_option_value(pid, gid):
    body = request.get_json(silent=True) or {}
    value = (body.get("value") or "").strip()
    if not value: return jsonify({"error": "값은 필수입니다."}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO product_option_values (group_id, value, sort_order) VALUES (%s, %s, %s) "
            "RETURNING id, value, sort_order",
            (str(gid), value, int(body.get("sort_order", 0))),
        )
        row = cur.fetchone()
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/products/<uuid:pid>/option-groups/<uuid:gid>/values/<uuid:vid>")
def update_option_value(pid, gid, vid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "value"      in body: fields["value"]      = body["value"].strip()
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE product_option_values SET {set_clause} WHERE id = %s AND group_id = %s "
            f"RETURNING id, value, sort_order",
            list(fields.values()) + [str(vid), str(gid)],
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "값을 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/products/<uuid:pid>/option-groups/<uuid:gid>/values/<uuid:vid>")
def delete_option_value(pid, gid, vid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM product_option_values WHERE id = %s AND group_id = %s RETURNING id",
            (str(vid), str(gid)),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "값을 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


@bp.post("/api/products/<uuid:pid>/skus")
def create_sku(pid):
    body = request.get_json(silent=True) or {}
    sku_code = (body.get("sku_code") or "").strip()
    if not sku_code: return jsonify({"error": "SKU 코드는 필수입니다."}), 400
    option_value_ids = body.get("option_value_ids", [])
    price_raw = body.get("price_override")
    price_override = float(price_raw) if price_raw not in (None, "") else None
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO product_skus (product_id, sku_code, price_override) VALUES (%s, %s, %s) "
                "RETURNING id, sku_code, price_override",
                (str(pid), sku_code, price_override),
            )
            sku = _row(cur.fetchone())
            for vid in option_value_ids:
                cur.execute(
                    "INSERT INTO sku_option_values (sku_id, option_value_id) VALUES (%s, %s)",
                    (sku["id"], str(vid)),
                )
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "SKU 코드가 이미 존재합니다."}), 409
    return jsonify({"data": sku}), 201


@bp.put("/api/products/<uuid:pid>/skus/<uuid:sid>")
def update_sku(pid, sid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "sku_code" in body: fields["sku_code"] = body["sku_code"].strip()
    if "price_override" in body:
        pr = body["price_override"]
        fields["price_override"] = float(pr) if pr not in (None, "") else None
    option_value_ids = body.get("option_value_ids")
    try:
        with get_cursor(commit=True) as cur:
            if fields:
                set_clause = ", ".join(f"{k} = %s" for k in fields)
                cur.execute(
                    f"UPDATE product_skus SET {set_clause} WHERE id = %s AND product_id = %s "
                    f"RETURNING id, sku_code, price_override",
                    list(fields.values()) + [str(sid), str(pid)],
                )
                if not cur.fetchone():
                    return jsonify({"error": "SKU를 찾을 수 없습니다."}), 404
            if option_value_ids is not None:
                cur.execute("DELETE FROM sku_option_values WHERE sku_id = %s", (str(sid),))
                for vid in option_value_ids:
                    cur.execute(
                        "INSERT INTO sku_option_values (sku_id, option_value_id) VALUES (%s, %s)",
                        (str(sid), str(vid)),
                    )
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "SKU 코드가 이미 존재합니다."}), 409
    with get_cursor() as cur:
        cur.execute("SELECT id, sku_code, price_override FROM product_skus WHERE id = %s", (str(sid),))
        row = cur.fetchone()
    return jsonify({"data": _row(row)})


@bp.delete("/api/products/<uuid:pid>/skus/<uuid:sid>")
def delete_sku(pid, sid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM product_skus WHERE id = %s AND product_id = %s RETURNING id",
            (str(sid), str(pid)),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "SKU를 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


# ── Outfits API ────────────────────────────────────────────────────────────────

@bp.get("/api/outfits")
def list_outfits():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()

    conds, params = ["o.is_deleted = FALSE"], []
    if search: conds.append("o.name ILIKE %s"); params.append(f"%{search}%")
    where = "WHERE " + " AND ".join(conds)

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM outfits o {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT o.id, o.name, o.slug, o.description, o.discount_rate, o.is_active,
                       o.created_at, o.updated_at,
                       COUNT(oi.id) AS item_count,
                       COALESCE(
                           o.thumbnail_url,
                           (SELECT pi.image_url FROM outfit_items oi2
                            JOIN product_images pi ON pi.product_id = oi2.product_id AND pi.is_thumbnail = TRUE
                            WHERE oi2.outfit_id = o.id ORDER BY oi2.sort_order LIMIT 1)
                       ) AS thumbnail_url
                FROM outfits o
                LEFT JOIN outfit_items oi ON oi.outfit_id = o.id
                {where} GROUP BY o.id ORDER BY o.created_at DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows), "pagination": _pg(page, limit, total)})


@bp.get("/api/outfits/<uuid:oid>")
def get_outfit(oid):
    oid_s = str(oid)
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, slug, description, discount_rate, is_active, created_at, updated_at "
            "FROM outfits WHERE id = %s AND is_deleted = FALSE",
            (oid_s,),
        )
        outfit = cur.fetchone()
        if not outfit: return jsonify({"error": "코디를 찾을 수 없습니다."}), 404
        outfit = _row(outfit)
        cur.execute(
            """SELECT oi.id AS item_id, oi.sort_order, oi.product_id, oi.sku_id,
                      p.name AS product_name, p.base_price, p.discount_price,
                      ps.sku_code, ps.price_override,
                      (SELECT pi.image_url FROM product_images pi
                       WHERE pi.product_id = p.id AND pi.is_thumbnail = TRUE LIMIT 1) AS thumbnail_url
               FROM outfit_items oi
               JOIN products p ON p.id = oi.product_id
               LEFT JOIN product_skus ps ON ps.id = oi.sku_id
               WHERE oi.outfit_id = %s ORDER BY oi.sort_order""",
            (oid_s,),
        )
        outfit["items"] = _rows(cur.fetchall())
    return jsonify({"data": outfit})


@bp.post("/api/outfits")
def create_outfit():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    slug = (body.get("slug") or "").strip()
    if not name or not slug:
        return jsonify({"error": "이름과 slug는 필수입니다."}), 400
    dr = body.get("discount_rate")
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO outfits (name, slug, description, discount_rate, is_active)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, name, slug, description, discount_rate, is_active, created_at""",
                (name, slug, body.get("description") or None,
                 float(dr) if dr not in (None, "") else 0,
                 bool(body.get("is_active", True))),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/outfits/<uuid:oid>")
def update_outfit(oid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "name"          in body: fields["name"]          = body["name"].strip()
    if "slug"          in body: fields["slug"]          = body["slug"].strip()
    if "description"   in body: fields["description"]   = body["description"] or None
    if "discount_rate" in body:
        dr = body["discount_rate"]
        fields["discount_rate"] = float(dr) if dr not in (None, "") else 0
    if "is_active"     in body: fields["is_active"]     = bool(body["is_active"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE outfits SET {set_clause} WHERE id = %s AND is_deleted = FALSE "
                f"RETURNING id, name, slug, description, discount_rate, is_active, updated_at",
                list(fields.values()) + [str(oid)],
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "slug가 이미 존재합니다."}), 409
    if not row: return jsonify({"error": "코디를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.post("/api/outfits/<uuid:oid>/thumbnail")
def upload_outfit_thumbnail(oid):
    oid_s = str(oid)
    with get_cursor() as cur:
        cur.execute("SELECT id FROM outfits WHERE id = %s AND is_deleted = FALSE", (oid_s,))
        if not cur.fetchone():
            return jsonify({"error": "코디를 찾을 수 없습니다."}), 404
    file = request.files.get("image")
    if not file:
        return jsonify({"error": "이미지 파일이 없습니다."}), 400
    try:
        from services.s3_service import upload_image
        image_url = upload_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE outfits SET thumbnail_url = %s, updated_at = NOW() WHERE id = %s AND is_deleted = FALSE RETURNING thumbnail_url",
            (image_url, oid_s),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "코디를 찾을 수 없습니다."}), 404
    return jsonify({"thumbnail_url": row["thumbnail_url"]}), 200


@bp.delete("/api/outfits/<uuid:oid>")
def delete_outfit(oid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE outfits SET is_deleted = TRUE, is_active = FALSE "
            "WHERE id = %s AND is_deleted = FALSE RETURNING id",
            (str(oid),),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "코디를 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


# ── Outfit Items API ───────────────────────────────────────────────────────────

@bp.get("/api/outfits/<uuid:oid>/products")
def list_products_for_outfit(oid):
    """아이템 추가 모달에서 상품 검색용."""
    q = request.args.get("q", "").strip()
    conds, params = ["is_deleted = FALSE", "is_active = TRUE"], []
    if q: conds.append("name ILIKE %s"); params.append(f"%{q}%")
    with get_cursor() as cur:
        cur.execute(
            f"SELECT id, name, base_price, discount_price FROM products WHERE {' AND '.join(conds)} "
            f"ORDER BY name LIMIT 50",
            params,
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows)})


@bp.get("/api/products/<uuid:pid>/skus-list")
def list_skus_for_product(pid):
    """아이템 추가 모달에서 SKU 선택용."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, sku_code, price_override FROM product_skus WHERE product_id = %s ORDER BY sku_code",
            (str(pid),),
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows)})


@bp.post("/api/outfits/<uuid:oid>/items")
def add_outfit_item(oid):
    body = request.get_json(silent=True) or {}
    product_id = body.get("product_id")
    if not product_id: return jsonify({"error": "product_id는 필수입니다."}), 400
    sku_id = body.get("sku_id") or None
    with get_cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(sort_order) + 1, 0) AS next_sort FROM outfit_items WHERE outfit_id = %s",
            (str(oid),),
        )
        next_sort = cur.fetchone()["next_sort"]
    sort_order = int(body.get("sort_order", next_sort))
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO outfit_items (outfit_id, product_id, sku_id, sort_order) VALUES (%s, %s, %s, %s) "
            "RETURNING id, outfit_id, product_id, sku_id, sort_order",
            (str(oid), str(product_id), str(sku_id) if sku_id else None, sort_order),
        )
        row = cur.fetchone()
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/outfits/<uuid:oid>/items/<uuid:iid>")
def update_outfit_item(oid, iid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "sku_id"     in body: fields["sku_id"]     = body["sku_id"] or None
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if not fields: return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE outfit_items SET {set_clause} WHERE id = %s AND outfit_id = %s "
            f"RETURNING id, outfit_id, product_id, sku_id, sort_order",
            list(fields.values()) + [str(iid), str(oid)],
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "아이템을 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/outfits/<uuid:oid>/items/<uuid:iid>")
def delete_outfit_item(oid, iid):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM outfit_items WHERE id = %s AND outfit_id = %s RETURNING id",
            (str(iid), str(oid)),
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "아이템을 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


# ── Cart API (Read-only) ───────────────────────────────────────────────────────

@bp.get("/api/cart")
def list_carts():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    search = request.args.get("search", "").strip()

    conds, params = [], []
    if search:
        conds.append("(u.email ILIKE %s OR u.name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS total FROM cart c LEFT JOIN users u ON u.id = c.user_id {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT c.id, c.user_id, u.email AS user_email, u.name AS user_name,
                       COUNT(ci.id) AS item_count, c.created_at, c.updated_at
                FROM cart c
                LEFT JOIN users u ON u.id = c.user_id
                LEFT JOIN cart_items ci ON ci.cart_id = c.id
                {where}
                GROUP BY c.id, u.email, u.name
                ORDER BY c.updated_at DESC NULLS LAST LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows), "pagination": _pg(page, limit, total)})


@bp.get("/api/cart/<uuid:cid>")
def get_cart(cid):
    cid_s = str(cid)
    with get_cursor() as cur:
        cur.execute(
            """SELECT c.id, c.user_id, u.email AS user_email, u.name AS user_name, c.created_at
               FROM cart c LEFT JOIN users u ON u.id = c.user_id WHERE c.id = %s""",
            (cid_s,),
        )
        cart = cur.fetchone()
        if not cart: return jsonify({"error": "장바구니를 찾을 수 없습니다."}), 404
        cart = _row(cart)
        cur.execute(
            """SELECT ci.id, ci.product_id, p.name AS product_name, p.base_price,
                      ci.sku_id, ps.sku_code, ci.quantity,
                      (SELECT pi.image_url FROM product_images pi
                       WHERE pi.product_id = p.id AND pi.is_thumbnail = TRUE LIMIT 1) AS thumbnail_url
               FROM cart_items ci
               JOIN products p ON p.id = ci.product_id
               LEFT JOIN product_skus ps ON ps.id = ci.sku_id
               WHERE ci.cart_id = %s ORDER BY ci.created_at""",
            (cid_s,),
        )
        cart["items"] = _rows(cur.fetchall())
    return jsonify({"data": cart})


# ── Orders API ─────────────────────────────────────────────────────────────────

@bp.get("/api/orders")
def list_orders():
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    status = request.args.get("status", "").strip()
    search = request.args.get("search", "").strip()

    conds, params = [], []
    if status: conds.append("o.status = %s"); params.append(status)
    if search:
        conds.append("(u.email ILIKE %s OR u.name ILIKE %s OR o.order_number ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS total FROM orders o LEFT JOIN users u ON u.id = o.user_id {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT o.id, o.order_number, o.status, o.total_amount, o.discount_amount,
                       o.shipping_fee, o.final_amount, o.payment_method, o.paid_at,
                       o.created_at, u.email AS user_email, u.name AS user_name
                FROM orders o LEFT JOIN users u ON u.id = o.user_id
                {where} ORDER BY o.created_at DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows), "pagination": _pg(page, limit, total)})


@bp.get("/api/orders/<uuid:oid>")
def get_order(oid):
    oid_s = str(oid)
    with get_cursor() as cur:
        cur.execute(
            """SELECT o.id, o.order_number, o.status, o.total_amount, o.discount_amount,
                      o.shipping_fee, o.final_amount, o.payment_method, o.payment_key, o.paid_at,
                      o.recipient, o.phone, o.zip_code, o.address1, o.address2,
                      o.user_memo, o.admin_memo, o.created_at, o.updated_at,
                      u.email AS user_email, u.name AS user_name
               FROM orders o LEFT JOIN users u ON u.id = o.user_id WHERE o.id = %s""",
            (oid_s,),
        )
        order = cur.fetchone()
        if not order: return jsonify({"error": "주문을 찾을 수 없습니다."}), 404
        order = _row(order)
        cur.execute(
            "SELECT id, product_name, sku_code, option_summary, unit_price, quantity, subtotal "
            "FROM order_items WHERE order_id = %s ORDER BY created_at",
            (oid_s,),
        )
        order["items"] = _rows(cur.fetchall())
    return jsonify({"data": order})


@bp.put("/api/orders/<uuid:oid>/status")
def update_order_status(oid):
    body   = request.get_json(silent=True) or {}
    status = (body.get("status") or "").strip()
    VALID  = {"PENDING", "PAID", "PREPARING", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"}
    if status not in VALID:
        return jsonify({"error": f"유효하지 않은 상태입니다. ({', '.join(sorted(VALID))})"}), 400
    fields = {"status": status}
    if "admin_memo" in body: fields["admin_memo"] = body["admin_memo"]
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE orders SET {set_clause} WHERE id = %s "
            f"RETURNING id, order_number, status, admin_memo, updated_at",
            list(fields.values()) + [str(oid)],
        )
        row = cur.fetchone()
    if not row: return jsonify({"error": "주문을 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


# ── Banners HTML Page ──────────────────────────────────────────────────────────

@bp.get("/banners")
def banners_page():
    return render_template("admin/banners.html")


# ── Banners API ────────────────────────────────────────────────────────────────

@bp.get("/api/banners")
def list_banners():
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, title, image_url, outfit_id, link_url, sort_order, is_active,
                      created_at, updated_at
               FROM banners ORDER BY sort_order ASC"""
        )
        rows = cur.fetchall()
    return jsonify({"data": _rows(rows)})


@bp.post("/api/banners")
def create_banner():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "제목은 필수입니다."}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO banners (title, outfit_id, link_url, sort_order, is_active)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, title, image_url, outfit_id, link_url, sort_order, is_active,
                         created_at, updated_at""",
            (title, body.get("outfit_id") or None, body.get("link_url") or None,
             int(body.get("sort_order", 0)), bool(body.get("is_active", True))),
        )
        row = cur.fetchone()
    return jsonify({"data": _row(row)}), 201


@bp.put("/api/banners/<uuid:bid>")
def update_banner(bid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "title"      in body: fields["title"]      = body["title"].strip()
    if "outfit_id"  in body: fields["outfit_id"]  = body["outfit_id"] or None
    if "link_url"   in body: fields["link_url"]   = body["link_url"] or None
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if "is_active"  in body: fields["is_active"]  = bool(body["is_active"])
    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400
    set_clause = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE banners SET {set_clause} WHERE id = %s "
            f"RETURNING id, title, image_url, outfit_id, link_url, sort_order, is_active, updated_at",
            list(fields.values()) + [str(bid)],
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "배너를 찾을 수 없습니다."}), 404
    return jsonify({"data": _row(row)})


@bp.delete("/api/banners/<uuid:bid>")
def delete_banner(bid):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM banners WHERE id = %s RETURNING id", (str(bid),))
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "배너를 찾을 수 없습니다."}), 404
    return jsonify({"message": "삭제되었습니다."})


@bp.post("/api/banners/<uuid:bid>/image")
def upload_banner_image(bid):
    bid_s = str(bid)
    with get_cursor() as cur:
        cur.execute("SELECT id FROM banners WHERE id = %s", (bid_s,))
        if not cur.fetchone():
            return jsonify({"error": "배너를 찾을 수 없습니다."}), 404
    file = request.files.get("image")
    if not file:
        return jsonify({"error": "이미지 파일이 없습니다."}), 400
    try:
        from services.s3_service import upload_image
        image_url = upload_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE banners SET image_url = %s, updated_at = NOW() WHERE id = %s RETURNING image_url",
            (image_url, bid_s),
        )
        row = cur.fetchone()
    return jsonify({"image_url": row["image_url"]}), 200
