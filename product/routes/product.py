from flask import Blueprint, request, jsonify
from database import get_cursor, get_db
from services.sftp_service import upload_image, delete_image
from psycopg2.extras import RealDictCursor
import psycopg2

bp = Blueprint("product", __name__, url_prefix="/")


def _stringify_uuids(row: dict, *keys) -> dict:
    d = dict(row)
    for key in keys:
        if d.get(key) is not None:
            d[key] = str(d[key])
    return d


# ─────────────────────────────────────────────
# GET /product
# 쿼리 파라미터:
#   category_id  → 특정 카테고리 필터
#   search       → 상품명 트라이그램 검색
#   page         → 페이지 번호 (기본 1)
#   limit        → 페이지당 개수 (기본 20, 최대 100)
# ─────────────────────────────────────────────
@bp.get("")
def list_products():
    category_id = request.args.get("category_id")
    search      = request.args.get("search", "").strip()
    page        = max(1, int(request.args.get("page", 1)))
    limit       = min(100, max(1, int(request.args.get("limit", 20))))
    offset      = (page - 1) * limit

    conditions = ["p.is_deleted = FALSE"]
    params: list = []

    if category_id:
        conditions.append("p.category_id = %s")
        params.append(category_id)

    if search:
        conditions.append("p.name ILIKE %s")
        params.append(f"%{search}%")

    where = "WHERE " + " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM products p
            {where}
            """,
            params,
        )
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT p.id, p.category_id, p.name, p.slug, p.description,
                   p.base_price, p.discount_price, p.is_active, p.created_at, p.updated_at,
                   c.name AS category_name,
                   (
                       SELECT image_url FROM product_images
                       WHERE product_id = p.id AND is_thumbnail = TRUE
                       ORDER BY sort_order LIMIT 1
                   ) AS thumbnail_url
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            {where}
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    items = [
        _stringify_uuids(r, "id", "category_id")
        for r in rows
    ]

    return jsonify({
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
        },
    })


# ─────────────────────────────────────────────
# GET /product/<id>
# 이미지, 옵션 그룹, 옵션 값, SKU 포함 반환
# ─────────────────────────────────────────────
@bp.get("/<uuid:product_id>")
def get_product(product_id):
    pid = str(product_id)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.category_id, p.name, p.slug, p.description,
                   p.base_price, p.discount_price, p.is_active, p.is_deleted,
                   p.created_at, p.updated_at,
                   c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.id = %s AND p.is_deleted = FALSE
            """,
            (pid,),
        )
        product = cur.fetchone()
        if not product:
            return jsonify({"error": "상품을 찾을 수 없습니다."}), 404

        product = _stringify_uuids(product, "id", "category_id")

        # 이미지
        cur.execute(
            """
            SELECT id, image_url, alt_text, sort_order, is_thumbnail, created_at
            FROM product_images
            WHERE product_id = %s
            ORDER BY sort_order, created_at
            """,
            (pid,),
        )
        product["images"] = [_stringify_uuids(r, "id") for r in cur.fetchall()]

        # 옵션 그룹 + 옵션 값
        cur.execute(
            """
            SELECT g.id AS group_id, g.name AS group_name, g.sort_order AS group_sort,
                   v.id AS value_id, v.value, v.sort_order AS value_sort
            FROM product_option_groups g
            LEFT JOIN product_option_values v ON v.group_id = g.id
            WHERE g.product_id = %s
            ORDER BY g.sort_order, v.sort_order
            """,
            (pid,),
        )
        option_rows = cur.fetchall()
        groups: dict = {}
        for row in option_rows:
            gid = str(row["group_id"])
            if gid not in groups:
                groups[gid] = {
                    "id": gid,
                    "name": row["group_name"],
                    "sort_order": row["group_sort"],
                    "values": [],
                }
            if row["value_id"]:
                groups[gid]["values"].append({
                    "id": str(row["value_id"]),
                    "value": row["value"],
                    "sort_order": row["value_sort"],
                })
        product["option_groups"] = list(groups.values())

        # SKU
        cur.execute(
            """
            SELECT s.id, s.sku_code, s.price_override, s.created_at, s.updated_at,
                   COALESCE(
                       json_agg(v.value ORDER BY v.sort_order) FILTER (WHERE v.id IS NOT NULL),
                       '[]'
                   ) AS option_values
            FROM product_skus s
            LEFT JOIN sku_option_values sov ON sov.sku_id = s.id
            LEFT JOIN product_option_values v ON v.id = sov.option_value_id
            WHERE s.product_id = %s
            GROUP BY s.id
            ORDER BY s.created_at
            """,
            (pid,),
        )
        product["skus"] = [_stringify_uuids(r, "id") for r in cur.fetchall()]

    return jsonify({"data": product})


# ─────────────────────────────────────────────
# POST /product
# Body (JSON):
#   name* slug* category_id* base_price*
#   description discount_price is_active
# ─────────────────────────────────────────────
@bp.post("")
def create_product():
    body = request.get_json(silent=True) or {}

    name        = body.get("name", "").strip()
    slug        = body.get("slug", "").strip()
    category_id = body.get("category_id")
    base_price  = body.get("base_price")

    if not all([name, slug, category_id, base_price is not None]):
        return jsonify({"error": "name, slug, category_id, base_price는 필수입니다."}), 400

    description    = body.get("description")
    discount_price = body.get("discount_price")
    is_active      = bool(body.get("is_active", True))

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO products
                    (category_id, name, slug, description, base_price, discount_price, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, category_id, name, slug, description,
                          base_price, discount_price, is_active, is_deleted,
                          created_at, updated_at
                """,
                (category_id, name, slug, description, base_price, discount_price, is_active),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "category_id가 유효하지 않습니다."}), 400

    return jsonify({"data": _stringify_uuids(row, "id", "category_id")}), 201


# ─────────────────────────────────────────────
# PUT /product/<id>
# ─────────────────────────────────────────────
@bp.put("/<uuid:product_id>")
def update_product(product_id):
    body = request.get_json(silent=True) or {}

    fields = {}
    if "name"           in body: fields["name"]           = body["name"].strip()
    if "slug"           in body: fields["slug"]           = body["slug"].strip()
    if "category_id"    in body: fields["category_id"]    = body["category_id"]
    if "description"    in body: fields["description"]    = body["description"]
    if "base_price"     in body: fields["base_price"]     = body["base_price"]
    if "discount_price" in body: fields["discount_price"] = body["discount_price"]
    if "is_active"      in body: fields["is_active"]      = bool(body["is_active"])

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [str(product_id)]

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"""
                UPDATE products
                SET {set_clause}
                WHERE id = %s AND is_deleted = FALSE
                RETURNING id, category_id, name, slug, description,
                          base_price, discount_price, is_active, created_at, updated_at
                """,
                values,
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "category_id가 유효하지 않습니다."}), 400

    if not row:
        return jsonify({"error": "상품을 찾을 수 없습니다."}), 404

    return jsonify({"data": _stringify_uuids(row, "id", "category_id")})


# ─────────────────────────────────────────────
# DELETE /product/<id>   (소프트 삭제)
# ─────────────────────────────────────────────
@bp.delete("/<uuid:product_id>")
def delete_product(product_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE products
            SET is_deleted = TRUE, is_active = FALSE
            WHERE id = %s AND is_deleted = FALSE
            RETURNING id
            """,
            (str(product_id),),
        )
        deleted = cur.fetchone()

    if not deleted:
        return jsonify({"error": "상품을 찾을 수 없습니다."}), 404

    return "", 204


# ─────────────────────────────────────────────
# POST /product/<id>/images
# Content-Type: multipart/form-data
#   image*       → 이미지 파일
#   alt_text     → 대체 텍스트
#   sort_order   → 정렬 순서
#   is_thumbnail → 썸네일 여부 (true/false)
# ─────────────────────────────────────────────
@bp.post("/<uuid:product_id>/images")
def upload_product_image(product_id):
    pid = str(product_id)

    # 상품 존재 확인
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM products WHERE id = %s AND is_deleted = FALSE",
            (pid,),
        )
        if not cur.fetchone():
            return jsonify({"error": "상품을 찾을 수 없습니다."}), 404

    file = request.files.get("image")
    if not file:
        return jsonify({"error": "image 파일이 필요합니다."}), 400

    alt_text     = request.form.get("alt_text", "")
    sort_order   = int(request.form.get("sort_order", 0))
    is_thumbnail = request.form.get("is_thumbnail", "false").lower() == "true"

    try:
        image_url = upload_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # 썸네일로 지정 시 기존 썸네일 해제
    with get_cursor(commit=True) as cur:
        if is_thumbnail:
            cur.execute(
                "UPDATE product_images SET is_thumbnail = FALSE WHERE product_id = %s",
                (pid,),
            )
        cur.execute(
            """
            INSERT INTO product_images
                (product_id, image_url, alt_text, sort_order, is_thumbnail)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, product_id, image_url, alt_text, sort_order, is_thumbnail, created_at
            """,
            (pid, image_url, alt_text, sort_order, is_thumbnail),
        )
        row = cur.fetchone()

    return jsonify({"data": _stringify_uuids(row, "id", "product_id")}), 201


# ─────────────────────────────────────────────
# DELETE /product/<product_id>/images/<image_id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:product_id>/images/<uuid:image_id>")
def delete_product_image(product_id, image_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM product_images
            WHERE id = %s AND product_id = %s
            RETURNING image_url
            """,
            (str(image_id), str(product_id)),
        )
        deleted = cur.fetchone()

    if not deleted:
        return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404

    try:
        delete_image(deleted["image_url"])
    except Exception:
        # SFTP 삭제 실패해도 DB 레코드는 이미 삭제됐으므로 경고만 기록
        pass

    return "", 204


# =============================================================
# 옵션 그룹 / 옵션 값 / SKU API
# =============================================================

# ─────────────────────────────────────────────
# GET /product/<id>/options
# 옵션 그룹·값·SKU 전체를 한 번에 반환
# ─────────────────────────────────────────────
@bp.get("/<uuid:product_id>/options")
def get_options(product_id):
    pid = str(product_id)
    with get_cursor() as cur:
        # 옵션 그룹 + 값
        cur.execute(
            """
            SELECT g.id AS group_id, g.name AS group_name, g.sort_order AS group_sort,
                   v.id AS value_id, v.value, v.sort_order AS value_sort
            FROM product_option_groups g
            LEFT JOIN product_option_values v ON v.group_id = g.id
            WHERE g.product_id = %s
            ORDER BY g.sort_order, v.sort_order
            """,
            (pid,),
        )
        groups: dict = {}
        for row in cur.fetchall():
            gid = str(row["group_id"])
            if gid not in groups:
                groups[gid] = {
                    "id": gid,
                    "name": row["group_name"],
                    "sort_order": row["group_sort"],
                    "values": [],
                }
            if row["value_id"]:
                groups[gid]["values"].append({
                    "id": str(row["value_id"]),
                    "value": row["value"],
                    "sort_order": row["value_sort"],
                })

        # SKU + 매핑된 옵션 값
        cur.execute(
            """
            SELECT s.id, s.sku_code, s.price_override,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'id',         v.id::text,
                               'value',      v.value,
                               'group_id',   g.id::text,
                               'group_name', g.name
                           ) ORDER BY g.sort_order, v.sort_order
                       ) FILTER (WHERE v.id IS NOT NULL),
                       '[]'
                   ) AS option_values
            FROM product_skus s
            LEFT JOIN sku_option_values   sov ON sov.sku_id         = s.id
            LEFT JOIN product_option_values v  ON v.id               = sov.option_value_id
            LEFT JOIN product_option_groups g  ON g.id               = v.group_id
            WHERE s.product_id = %s
            GROUP BY s.id
            ORDER BY s.sku_code
            """,
            (pid,),
        )
        skus = []
        for row in cur.fetchall():
            d = dict(row)
            d["id"] = str(d["id"])
            skus.append(d)

    return jsonify({"data": {"groups": list(groups.values()), "skus": skus}})


# ─────────────────────────────────────────────
# POST /product/<id>/option-groups
# Body: { name*, sort_order }
# ─────────────────────────────────────────────
@bp.post("/<uuid:product_id>/option-groups")
def create_option_group(product_id):
    pid  = str(product_id)
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name은 필수입니다."}), 400
    sort_order = int(body.get("sort_order", 0))

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO product_option_groups (product_id, name, sort_order)
            VALUES (%s, %s, %s)
            RETURNING id, product_id, name, sort_order
            """,
            (pid, name, sort_order),
        )
        row = _stringify_uuids(cur.fetchone(), "id", "product_id")
    return jsonify({"data": {**row, "values": []}}), 201


# ─────────────────────────────────────────────
# PUT /product/<id>/option-groups/<group_id>
# Body: { name, sort_order }
# ─────────────────────────────────────────────
@bp.put("/<uuid:product_id>/option-groups/<uuid:group_id>")
def update_option_group(product_id, group_id):
    body   = request.get_json(silent=True) or {}
    fields = {}
    if "name"       in body: fields["name"]       = body["name"].strip()
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [str(group_id), str(product_id)]

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            UPDATE product_option_groups SET {set_clause}
            WHERE id = %s AND product_id = %s
            RETURNING id, product_id, name, sort_order
            """,
            values,
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "옵션 그룹을 찾을 수 없습니다."}), 404
    return jsonify({"data": _stringify_uuids(row, "id", "product_id")})


# ─────────────────────────────────────────────
# DELETE /product/<id>/option-groups/<group_id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:product_id>/option-groups/<uuid:group_id>")
def delete_option_group(product_id, group_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM product_option_groups WHERE id = %s AND product_id = %s RETURNING id",
            (str(group_id), str(product_id)),
        )
        deleted = cur.fetchone()
    if not deleted:
        return jsonify({"error": "옵션 그룹을 찾을 수 없습니다."}), 404
    return "", 204


# ─────────────────────────────────────────────
# POST /product/<id>/option-groups/<group_id>/values
# Body: { value*, sort_order }
# ─────────────────────────────────────────────
@bp.post("/<uuid:product_id>/option-groups/<uuid:group_id>/values")
def create_option_value(product_id, group_id):
    body  = request.get_json(silent=True) or {}
    value = body.get("value", "").strip()
    if not value:
        return jsonify({"error": "value는 필수입니다."}), 400
    sort_order = int(body.get("sort_order", 0))

    with get_cursor(commit=True) as cur:
        # group이 해당 product에 속하는지 검증 후 삽입
        cur.execute(
            """
            INSERT INTO product_option_values (group_id, value, sort_order)
            SELECT %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM product_option_groups
                WHERE id = %s AND product_id = %s
            )
            RETURNING id, group_id, value, sort_order
            """,
            (str(group_id), value, sort_order, str(group_id), str(product_id)),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "옵션 그룹을 찾을 수 없습니다."}), 404
    return jsonify({"data": _stringify_uuids(row, "id", "group_id")}), 201


# ─────────────────────────────────────────────
# PUT /product/<id>/option-groups/<group_id>/values/<value_id>
# Body: { value, sort_order }
# ─────────────────────────────────────────────
@bp.put("/<uuid:product_id>/option-groups/<uuid:group_id>/values/<uuid:value_id>")
def update_option_value(product_id, group_id, value_id):
    body   = request.get_json(silent=True) or {}
    fields = {}
    if "value"      in body: fields["value"]      = body["value"].strip()
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"v.{k} = %s" for k in fields)
    params = list(fields.values()) + [str(value_id), str(group_id), str(product_id)]

    with get_cursor(commit=True) as cur:
        # product 소유권까지 JOIN으로 검증
        cur.execute(
            f"""
            UPDATE product_option_values v
            SET {set_clause}
            FROM product_option_groups g
            WHERE v.id = %s
              AND v.group_id = %s
              AND g.id = v.group_id
              AND g.product_id = %s
            RETURNING v.id, v.group_id, v.value, v.sort_order
            """,
            params,
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "옵션 값을 찾을 수 없습니다."}), 404
    return jsonify({"data": _stringify_uuids(row, "id", "group_id")})


# ─────────────────────────────────────────────
# DELETE /product/<id>/option-groups/<group_id>/values/<value_id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:product_id>/option-groups/<uuid:group_id>/values/<uuid:value_id>")
def delete_option_value(product_id, group_id, value_id):
    with get_cursor(commit=True) as cur:
        # product 소유권까지 서브쿼리로 검증
        cur.execute(
            """
            DELETE FROM product_option_values
            WHERE id = %s
              AND group_id = %s
              AND EXISTS (
                  SELECT 1 FROM product_option_groups
                  WHERE id = %s AND product_id = %s
              )
            RETURNING id
            """,
            (str(value_id), str(group_id), str(group_id), str(product_id)),
        )
        deleted = cur.fetchone()
    if not deleted:
        return jsonify({"error": "옵션 값을 찾을 수 없습니다."}), 404
    return "", 204


# ─────────────────────────────────────────────
# POST /product/<id>/skus
# Body: { sku_code*, price_override, option_value_ids[] }
# ─────────────────────────────────────────────
@bp.post("/<uuid:product_id>/skus")
def create_sku(product_id):
    pid  = str(product_id)
    body = request.get_json(silent=True) or {}

    sku_code = body.get("sku_code", "").strip()
    if not sku_code:
        return jsonify({"error": "sku_code는 필수입니다."}), 400

    price_override    = body.get("price_override") or None
    option_value_ids  = body.get("option_value_ids") or []

    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO product_skus (product_id, sku_code, price_override)
                    VALUES (%s, %s, %s)
                    RETURNING id, sku_code, price_override
                    """,
                    (pid, sku_code, price_override),
                )
                sku = dict(cur.fetchone())
                sku_id = str(sku["id"])
                sku["id"] = sku_id

                for vid in option_value_ids:
                    cur.execute(
                        "INSERT INTO sku_option_values (sku_id, option_value_id) VALUES (%s, %s)",
                        (sku_id, str(vid)),
                    )
            conn.commit()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 SKU 코드입니다."}), 409

    return jsonify({"data": sku}), 201


# ─────────────────────────────────────────────
# PUT /product/<id>/skus/<sku_id>
# Body: { sku_code, price_override, option_value_ids[] }
# ─────────────────────────────────────────────
@bp.put("/<uuid:product_id>/skus/<uuid:sku_id>")
def update_sku(product_id, sku_id):
    pid  = str(product_id)
    sid  = str(sku_id)
    body = request.get_json(silent=True) or {}

    fields: dict = {}
    if "sku_code"       in body: fields["sku_code"]       = body["sku_code"].strip()
    if "price_override" in body: fields["price_override"] = body["price_override"] or None

    option_value_ids = body.get("option_value_ids")   # None이면 매핑 변경 없음

    if not fields and option_value_ids is None:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if fields:
                    set_clause = ", ".join(f"{k} = %s" for k in fields)
                    cur.execute(
                        f"""
                        UPDATE product_skus SET {set_clause}
                        WHERE id = %s AND product_id = %s
                        RETURNING id, sku_code, price_override
                        """,
                        list(fields.values()) + [sid, pid],
                    )
                    if not cur.fetchone():
                        return jsonify({"error": "SKU를 찾을 수 없습니다."}), 404

                if option_value_ids is not None:
                    cur.execute("DELETE FROM sku_option_values WHERE sku_id = %s", (sid,))
                    for vid in option_value_ids:
                        cur.execute(
                            "INSERT INTO sku_option_values (sku_id, option_value_id) VALUES (%s, %s)",
                            (sid, str(vid)),
                        )
            conn.commit()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 SKU 코드입니다."}), 409

    return jsonify({"data": {"id": sid}})


# ─────────────────────────────────────────────
# DELETE /product/<id>/skus/<sku_id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:product_id>/skus/<uuid:sku_id>")
def delete_sku(product_id, sku_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM product_skus WHERE id = %s AND product_id = %s RETURNING id",
            (str(sku_id), str(product_id)),
        )
        deleted = cur.fetchone()
    if not deleted:
        return jsonify({"error": "SKU를 찾을 수 없습니다."}), 404
    return "", 204
