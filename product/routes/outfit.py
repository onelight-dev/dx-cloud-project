from flask import Blueprint, request, jsonify
from database import get_cursor
import psycopg2

bp = Blueprint("outfit", __name__, url_prefix="/outfit")


def _stringify_uuids(row: dict, *keys) -> dict:
    d = dict(row)
    for key in keys:
        if d.get(key) is not None:
            d[key] = str(d[key])
    return d


# ─────────────────────────────────────────────
# GET /outfit
# 쿼리 파라미터:
#   search  → 코디명 검색 (ILIKE)
#   page    → 페이지 번호 (기본 1)
#   limit   → 페이지당 개수 (기본 20, 최대 100)
# ─────────────────────────────────────────────
@bp.get("")
def list_outfits():
    search = request.args.get("search", "").strip()
    page   = max(1, int(request.args.get("page", 1)))
    limit  = min(100, max(1, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit

    conditions = ["o.is_deleted = FALSE", "o.is_active = TRUE"]
    params: list = []

    if search:
        conditions.append("o.name ILIKE %s")
        params.append(f"%{search}%")

    where = "WHERE " + " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS total FROM outfits o {where}",
            params,
        )
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT o.id, o.name, o.slug, o.description,
                   o.discount_rate, o.is_active, o.created_at, o.updated_at,
                   (
                       SELECT pi.image_url
                       FROM outfit_items oi2
                       JOIN product_images pi
                         ON pi.product_id = oi2.product_id
                        AND pi.is_thumbnail = TRUE
                       WHERE oi2.outfit_id = o.id
                       ORDER BY oi2.sort_order, pi.sort_order
                       LIMIT 1
                   ) AS thumbnail_url,
                   (
                       SELECT COUNT(*)
                       FROM outfit_items oi3
                       WHERE oi3.outfit_id = o.id
                   ) AS item_count
            FROM outfits o
            {where}
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    items = [_stringify_uuids(r, "id") for r in rows]

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
# GET /outfit/<id>
# 코디 단건 조회 (outfit_items + 상품 정보 포함)
# ─────────────────────────────────────────────
@bp.get("/<uuid:outfit_id>")
def get_outfit(outfit_id):
    oid = str(outfit_id)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, slug, description,
                   discount_rate, is_active, is_deleted,
                   created_at, updated_at
            FROM outfits
            WHERE id = %s AND is_deleted = FALSE
            """,
            (oid,),
        )
        outfit = cur.fetchone()
        if not outfit:
            return jsonify({"error": "코디를 찾을 수 없습니다."}), 404

        outfit = _stringify_uuids(outfit, "id")

        # outfit_items + 상품 기본 정보 + 썸네일
        cur.execute(
            """
            SELECT
                oi.id        AS item_id,
                oi.sort_order,
                oi.created_at AS item_created_at,
                p.id         AS product_id,
                p.name       AS product_name,
                p.slug       AS product_slug,
                p.base_price,
                p.discount_price,
                p.description AS product_description,
                s.id         AS sku_id,
                s.sku_code,
                s.price_override,
                (
                    SELECT image_url FROM product_images pi
                    WHERE pi.product_id = p.id AND pi.is_thumbnail = TRUE
                    ORDER BY pi.sort_order LIMIT 1
                ) AS thumbnail_url
            FROM outfit_items oi
            JOIN products     p ON p.id = oi.product_id
            LEFT JOIN product_skus s ON s.id = oi.sku_id
            WHERE oi.outfit_id = %s AND p.is_deleted = FALSE
            ORDER BY oi.sort_order, oi.created_at
            """,
            (oid,),
        )
        outfit["items"] = [
            _stringify_uuids(r, "item_id", "product_id", "sku_id")
            for r in cur.fetchall()
        ]

    return jsonify({"data": outfit})


# ─────────────────────────────────────────────
# POST /outfit
# 필수: name, slug
# 선택: description, discount_rate, is_active
# ─────────────────────────────────────────────
@bp.post("")
def create_outfit():
    body = request.get_json(silent=True) or {}

    name = body.get("name", "").strip()
    slug = body.get("slug", "").strip()

    if not name or not slug:
        return jsonify({"error": "name과 slug는 필수입니다."}), 400

    description   = body.get("description")
    discount_rate = body.get("discount_rate", 0)
    is_active     = bool(body.get("is_active", True))

    try:
        discount_rate = float(discount_rate)
        if not (0 <= discount_rate <= 100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "discount_rate는 0~100 사이의 숫자여야 합니다."}), 400

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO outfits (name, slug, description, discount_rate, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, slug, description,
                          discount_rate, is_active, is_deleted,
                          created_at, updated_at
                """,
                (name, slug, description, discount_rate, is_active),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409

    return jsonify({"data": _stringify_uuids(row, "id")}), 201


# ─────────────────────────────────────────────
# PUT /outfit/<id>
# 변경할 필드만 포함 (부분 수정)
# ─────────────────────────────────────────────
@bp.put("/<uuid:outfit_id>")
def update_outfit(outfit_id):
    body = request.get_json(silent=True) or {}

    fields: dict = {}
    if "name"          in body: fields["name"]          = body["name"].strip()
    if "slug"          in body: fields["slug"]          = body["slug"].strip()
    if "description"   in body: fields["description"]   = body["description"]
    if "is_active"     in body: fields["is_active"]     = bool(body["is_active"])
    if "discount_rate" in body:
        try:
            dr = float(body["discount_rate"])
            if not (0 <= dr <= 100):
                raise ValueError
            fields["discount_rate"] = dr
        except (TypeError, ValueError):
            return jsonify({"error": "discount_rate는 0~100 사이의 숫자여야 합니다."}), 400

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values     = list(fields.values()) + [str(outfit_id)]

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"""
                UPDATE outfits
                SET {set_clause}, updated_at = NOW()
                WHERE id = %s AND is_deleted = FALSE
                RETURNING id, name, slug, description,
                          discount_rate, is_active, created_at, updated_at
                """,
                values,
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409

    if not row:
        return jsonify({"error": "코디를 찾을 수 없습니다."}), 404

    return jsonify({"data": _stringify_uuids(row, "id")})


# ─────────────────────────────────────────────
# DELETE /outfit/<id>   (소프트 삭제)
# ─────────────────────────────────────────────
@bp.delete("/<uuid:outfit_id>")
def delete_outfit(outfit_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE outfits
            SET is_deleted = TRUE, is_active = FALSE, updated_at = NOW()
            WHERE id = %s AND is_deleted = FALSE
            RETURNING id
            """,
            (str(outfit_id),),
        )
        deleted = cur.fetchone()

    if not deleted:
        return jsonify({"error": "코디를 찾을 수 없습니다."}), 404

    return "", 204


# ═══════════════════════════════════════════════
#  outfit_items 관리
# ═══════════════════════════════════════════════

# ─────────────────────────────────────────────
# POST /outfit/<id>/items
# 필수: product_id
# 선택: sku_id, sort_order
# ─────────────────────────────────────────────
@bp.post("/<uuid:outfit_id>/items")
def add_outfit_item(outfit_id):
    oid  = str(outfit_id)
    body = request.get_json(silent=True) or {}

    product_id = body.get("product_id")
    if not product_id:
        return jsonify({"error": "product_id는 필수입니다."}), 400

    sku_id     = body.get("sku_id")
    sort_order = int(body.get("sort_order", 0))

    # 코디 존재 여부 확인
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM outfits WHERE id = %s AND is_deleted = FALSE",
            (oid,),
        )
        if not cur.fetchone():
            return jsonify({"error": "코디를 찾을 수 없습니다."}), 404

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO outfit_items (outfit_id, product_id, sku_id, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id, outfit_id, product_id, sku_id, sort_order, created_at
                """,
                (oid, product_id, sku_id, sort_order),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "해당 상품(옵션)이 이미 코디에 포함되어 있습니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "product_id 또는 sku_id가 유효하지 않습니다."}), 400

    return jsonify({"data": _stringify_uuids(row, "id", "outfit_id", "product_id", "sku_id")}), 201


# ─────────────────────────────────────────────
# PUT /outfit/<id>/items/<item_id>
# 변경 가능: sku_id, sort_order
# ─────────────────────────────────────────────
@bp.put("/<uuid:outfit_id>/items/<uuid:item_id>")
def update_outfit_item(outfit_id, item_id):
    body = request.get_json(silent=True) or {}

    fields: dict = {}
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if "sku_id"     in body: fields["sku_id"]     = body["sku_id"]  # None 허용

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values     = list(fields.values()) + [str(item_id), str(outfit_id)]

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"""
                UPDATE outfit_items
                SET {set_clause}
                WHERE id = %s AND outfit_id = %s
                RETURNING id, outfit_id, product_id, sku_id, sort_order, created_at
                """,
                values,
            )
            row = cur.fetchone()
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "sku_id가 유효하지 않습니다."}), 400
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "해당 상품(옵션)이 이미 코디에 포함되어 있습니다."}), 409

    if not row:
        return jsonify({"error": "코디 구성 상품을 찾을 수 없습니다."}), 404

    return jsonify({"data": _stringify_uuids(row, "id", "outfit_id", "product_id", "sku_id")})


# ─────────────────────────────────────────────
# DELETE /outfit/<id>/items/<item_id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:outfit_id>/items/<uuid:item_id>")
def delete_outfit_item(outfit_id, item_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM outfit_items
            WHERE id = %s AND outfit_id = %s
            RETURNING id
            """,
            (str(item_id), str(outfit_id)),
        )
        deleted = cur.fetchone()

    if not deleted:
        return jsonify({"error": "코디 구성 상품을 찾을 수 없습니다."}), 404

    return "", 204
