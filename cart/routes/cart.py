from flask import Blueprint, request, g
from common.decorators import auth_required
from common.responses import success, error
from services.cart_service import get_or_create_cart, get_cart_detail, add_cart_item, update_cart_item, delete_cart_item, clear_cart

cart_bp = Blueprint("cart", __name__)


@cart_bp.get("")
@auth_required
def get_cart():
    cart = get_or_create_cart(g.user_id)
    return success(get_cart_detail(cart["id"]))


@cart_bp.post("/items")
@auth_required
def add_item():
    payload = request.get_json(silent=True) or {}
    required = ["product_id", "quantity"]
    missing = [field for field in required if payload.get(field) in (None, "")]
    if missing:
        return error(f"Missing required fields: {', '.join(missing)}", 400)
    result = add_cart_item(g.user_id, payload)
    return success(result, "Cart item added", 201)


@cart_bp.put("/items/<item_id>")
@auth_required
def edit_item(item_id):
    payload = request.get_json(silent=True) or {}
    if payload.get("quantity") is None:
        return error("quantity is required", 400)
    result = update_cart_item(g.user_id, item_id, int(payload["quantity"]))
    if not result:
        return error("Cart item not found", 404)
    return success(result, "Cart item updated")


@cart_bp.delete("/items/<item_id>")
@auth_required
def remove_item(item_id):
    deleted = delete_cart_item(g.user_id, item_id)
    if not deleted:
        return error("Cart item not found", 404)
    return success(None, "Cart item deleted")


@cart_bp.delete("")
@auth_required
def remove_all_items():
    clear_cart(g.user_id)
    return success(None, "Cart cleared")
