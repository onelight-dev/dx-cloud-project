from flask import Blueprint, request, jsonify
from database import get_cursor
import psycopg2

bp = Blueprint("category", __name__, url_prefix="/")


def _category_row_to_dict(row: dict) -> dict:
    d = dict(row)
    for key in ("id", "parent_id"):
        if d.get(key):
            d[key] = str(d[key])
    return d


# ─────────────────────────────────────────────
# GET /category
# 쿼리 파라미터:
#   tree=true  → 계층 트리 반환
#   parent_id  → 특정 부모의 직속 자식만 반환
# ─────────────────────────────────────────────
@bp.get("")
def list_categories():
    tree_mode = request.args.get("tree", "").lower() == "true"
    parent_id = request.args.get("parent_id")

    with get_cursor() as cur:
        if parent_id:
            cur.execute(
                """
                SELECT id, parent_id, name, slug, description, sort_order, is_active,
                       created_at, updated_at
                FROM categories
                WHERE parent_id = %s
                ORDER BY sort_order, name
                """,
                (parent_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, parent_id, name, slug, description, sort_order, is_active,
                       created_at, updated_at
                FROM categories
                ORDER BY sort_order, name
                """
            )
        rows = [_category_row_to_dict(r) for r in cur.fetchall()]

    if tree_mode and not parent_id:
        rows = _build_tree(rows)

    return jsonify({"data": rows})


def _build_tree(flat: list[dict]) -> list[dict]:
    """평면 리스트를 parent_id 기준 트리 구조로 변환합니다."""
    index = {row["id"]: {**row, "children": []} for row in flat}
    roots = []
    for row in flat:
        pid = row.get("parent_id")
        if pid and pid in index:
            index[pid]["children"].append(index[row["id"]])
        else:
            roots.append(index[row["id"]])
    return roots


# ─────────────────────────────────────────────
# GET /category/<id>
# ─────────────────────────────────────────────
@bp.get("/<uuid:category_id>")
def get_category(category_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, parent_id, name, slug, description, sort_order, is_active,
                   created_at, updated_at
            FROM categories
            WHERE id = %s
            """,
            (str(category_id),),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404

    return jsonify({"data": _category_row_to_dict(row)})


# ─────────────────────────────────────────────
# GET /category/<id>/children
# ─────────────────────────────────────────────
@bp.get("/<uuid:category_id>/children")
def get_children(category_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, parent_id, name, slug, description, sort_order, is_active,
                   created_at, updated_at
            FROM categories
            WHERE parent_id = %s
            ORDER BY sort_order, name
            """,
            (str(category_id),),
        )
        rows = [_category_row_to_dict(r) for r in cur.fetchall()]

    return jsonify({"data": rows})


# ─────────────────────────────────────────────
# POST /category
# Body (JSON):
#   name* slug* parent_id description sort_order is_active
# ─────────────────────────────────────────────
@bp.post("")
def create_category():
    body = request.get_json(silent=True) or {}

    name = body.get("name", "").strip()
    slug = body.get("slug", "").strip()
    if not name or not slug:
        return jsonify({"error": "name과 slug는 필수입니다."}), 400

    parent_id   = body.get("parent_id") or None
    description = body.get("description")
    sort_order  = int(body.get("sort_order", 0))
    is_active   = bool(body.get("is_active", True))

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO categories (parent_id, name, slug, description, sort_order, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, parent_id, name, slug, description, sort_order, is_active,
                          created_at, updated_at
                """,
                (parent_id, name, slug, description, sort_order, is_active),
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "parent_id가 유효하지 않습니다."}), 400

    return jsonify({"data": _category_row_to_dict(row)}), 201


# ─────────────────────────────────────────────
# PUT /category/<id>
# ─────────────────────────────────────────────
@bp.put("/<uuid:category_id>")
def update_category(category_id):
    body = request.get_json(silent=True) or {}

    fields = {}
    if "name"        in body: fields["name"]        = body["name"].strip()
    if "slug"        in body: fields["slug"]        = body["slug"].strip()
    if "parent_id"   in body: fields["parent_id"]   = body["parent_id"] or None
    if "description" in body: fields["description"] = body["description"]
    if "sort_order"  in body: fields["sort_order"]  = int(body["sort_order"])
    if "is_active"   in body: fields["is_active"]   = bool(body["is_active"])

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [str(category_id)]

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"""
                UPDATE categories
                SET {set_clause}
                WHERE id = %s
                RETURNING id, parent_id, name, slug, description, sort_order, is_active,
                          created_at, updated_at
                """,
                values,
            )
            row = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "이미 사용 중인 slug입니다."}), 409
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "parent_id가 유효하지 않습니다."}), 400

    if not row:
        return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404

    return jsonify({"data": _category_row_to_dict(row)})


# ─────────────────────────────────────────────
# DELETE /category/<id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:category_id>")
def delete_category(category_id):
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "DELETE FROM categories WHERE id = %s RETURNING id",
                (str(category_id),),
            )
            deleted = cur.fetchone()
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({"error": "해당 카테고리에 연결된 상품이 있어 삭제할 수 없습니다."}), 409

    if not deleted:
        return jsonify({"error": "카테고리를 찾을 수 없습니다."}), 404

    return "", 204
