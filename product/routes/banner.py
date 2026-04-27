from flask import Blueprint, request, jsonify
from database import get_cursor
from services.s3_service import upload_image
import psycopg2

bp = Blueprint("banner", __name__, url_prefix="/banners")


def _row_to_dict(row: dict, *uuid_keys) -> dict:
    d = dict(row)
    for k in uuid_keys:
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


# ─────────────────────────────────────────────
# GET /api/banners — 활성 배너 목록 (프론트엔드용)
# ─────────────────────────────────────────────
@bp.get("")
def list_banners():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, title, image_url, outfit_id, link_url, sort_order, is_active
            FROM banners
            WHERE is_active = TRUE
            ORDER BY sort_order ASC
            """
        )
        rows = cur.fetchall()
    return jsonify([_row_to_dict(r, "id", "outfit_id") for r in rows]), 200


# ─────────────────────────────────────────────
# GET /api/banners/all — 전체 배너 (Admin용)
# ─────────────────────────────────────────────
@bp.get("/all")
def list_all_banners():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, title, image_url, outfit_id, link_url, sort_order, is_active,
                   created_at, updated_at
            FROM banners
            ORDER BY sort_order ASC
            """
        )
        rows = cur.fetchall()
    return jsonify({"data": [_row_to_dict(r, "id", "outfit_id") for r in rows]}), 200


# ─────────────────────────────────────────────
# POST /api/banners — 배너 생성
# Body: { title*, sort_order, outfit_id, link_url, is_active }
# ─────────────────────────────────────────────
@bp.post("")
def create_banner():
    body = request.get_json(silent=True) or {}
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"error": "title은 필수입니다."}), 400

    outfit_id  = body.get("outfit_id") or None
    link_url   = body.get("link_url") or None
    sort_order = int(body.get("sort_order", 0))
    is_active  = bool(body.get("is_active", True))

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO banners (title, outfit_id, link_url, sort_order, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, title, image_url, outfit_id, link_url, sort_order, is_active,
                      created_at, updated_at
            """,
            (title, outfit_id, link_url, sort_order, is_active),
        )
        row = cur.fetchone()

    return jsonify({"data": _row_to_dict(row, "id", "outfit_id")}), 201


# ─────────────────────────────────────────────
# PUT /api/banners/<id> — 배너 수정
# ─────────────────────────────────────────────
@bp.put("/<uuid:banner_id>")
def update_banner(banner_id):
    body = request.get_json(silent=True) or {}
    fields: dict = {}
    if "title"      in body: fields["title"]      = body["title"].strip()
    if "outfit_id"  in body: fields["outfit_id"]  = body["outfit_id"] or None
    if "link_url"   in body: fields["link_url"]   = body["link_url"] or None
    if "sort_order" in body: fields["sort_order"] = int(body["sort_order"])
    if "is_active"  in body: fields["is_active"]  = bool(body["is_active"])

    if not fields:
        return jsonify({"error": "수정할 필드가 없습니다."}), 400

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [str(banner_id)]

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            UPDATE banners
            SET {set_clause}, updated_at = NOW()
            WHERE id = %s
            RETURNING id, title, image_url, outfit_id, link_url, sort_order, is_active,
                      created_at, updated_at
            """,
            values,
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "배너를 찾을 수 없습니다."}), 404

    return jsonify({"data": _row_to_dict(row, "id", "outfit_id")}), 200


# ─────────────────────────────────────────────
# DELETE /api/banners/<id>
# ─────────────────────────────────────────────
@bp.delete("/<uuid:banner_id>")
def delete_banner(banner_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM banners WHERE id = %s RETURNING id",
            (str(banner_id),),
        )
        deleted = cur.fetchone()

    if not deleted:
        return jsonify({"error": "배너를 찾을 수 없습니다."}), 404

    return "", 204


# ─────────────────────────────────────────────
# POST /api/banners/<id>/image — 배너 이미지 업로드
# Content-Type: multipart/form-data, field: image
# ─────────────────────────────────────────────
@bp.post("/<uuid:banner_id>/image")
def upload_banner_image(banner_id):
    bid = str(banner_id)

    with get_cursor() as cur:
        cur.execute("SELECT id FROM banners WHERE id = %s", (bid,))
        if not cur.fetchone():
            return jsonify({"error": "배너를 찾을 수 없습니다."}), 404

    file = request.files.get("image")
    if not file:
        return jsonify({"error": "image 파일이 필요합니다."}), 400

    try:
        image_url = upload_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE banners SET image_url = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING image_url
            """,
            (image_url, bid),
        )
        row = cur.fetchone()

    return jsonify({"image_url": row["image_url"]}), 200
