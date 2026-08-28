from flask import Blueprint, jsonify, request

from wishlist.service import (
    add_wishlist_item,
    clear_wishlist,
    delete_wishlist_item,
    get_my_wishlist,
    update_wishlist_item,
)

wishlist_bp = Blueprint("wishlist", __name__)


@wishlist_bp.get("")
def get_wishlist():
    result = get_my_wishlist()
    return jsonify(result), 200


@wishlist_bp.post("/items")
def create_wishlist_item():
    payload = request.get_json(silent=True) or {}

    product_id = payload.get("product_id")
    sku_id = payload.get("sku_id")
    quantity = payload.get("quantity")

    if not product_id:
        return jsonify({"error": "product_id는 필수입니다."}), 400

    if not sku_id:
        return jsonify({"error": "sku_id는 필수입니다."}), 400

    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity는 1 이상 정수여야 합니다."}), 400

    result = add_wishlist_item(
        product_id=product_id,
        sku_id=sku_id,
        quantity=quantity,
    )
    status_code = 201 if "error" not in result else 400
    return jsonify(result), status_code


@wishlist_bp.patch("/items/<item_id>")
def patch_wishlist_item(item_id):
    payload = request.get_json(silent=True) or {}
    quantity = payload.get("quantity")

    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity는 1 이상 정수여야 합니다."}), 400

    result = update_wishlist_item(item_id=item_id, quantity=quantity)
    status_code = 200 if "error" not in result else 404
    return jsonify(result), status_code


@wishlist_bp.delete("/items/<item_id>")
def remove_wishlist_item(item_id):
    result = delete_wishlist_item(item_id=item_id)
    status_code = 200 if "error" not in result else 404
    return jsonify(result), status_code


@wishlist_bp.delete("")
def delete_all_wishlist_items():
    result = clear_wishlist()
    return jsonify(result), 200