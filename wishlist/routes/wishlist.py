from flask import Blueprint, request, g
from common.decorators import auth_required
from common.responses import success, error
from services.wishlist_service import list_wishlist_items, add_wishlist_item, delete_wishlist_item

wishlist_bp = Blueprint("wishlist", __name__)


@wishlist_bp.get("")
@auth_required
def get_wishlist():
    return success(list_wishlist_items(g.user_id))


@wishlist_bp.post("")
@auth_required
def add_item():
    payload = request.get_json(silent=True) or {}
    if not payload.get("product_id"):
        return error("product_id is required", 400)
    result = add_wishlist_item(g.user_id, payload["product_id"])
    return success(result, "Wishlist item added", 201)


@wishlist_bp.delete("/<wishlist_item_id>")
@auth_required
def remove_item(wishlist_item_id):
    deleted = delete_wishlist_item(g.user_id, wishlist_item_id)
    if not deleted:
        return error("Wishlist item not found", 404)
    return success(None, "Wishlist item deleted")
