from flask import Blueprint, request, g
from common.decorators import auth_required
from common.responses import success, error
from services.address_service import list_addresses, create_address, update_address, delete_address

addresses_bp = Blueprint("addresses", __name__)


@addresses_bp.get("")
@auth_required
def get_addresses():
    return success(list_addresses(g.user_id))


@addresses_bp.post("")
@auth_required
def add_address():
    payload = request.get_json(silent=True) or {}
    required = ["recipient_name", "phone", "zip_code", "address1"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        return error(f"Missing required fields: {', '.join(missing)}", 400)
    result = create_address(g.user_id, payload)
    return success(result, "Address created", 201)


@addresses_bp.put("/<address_id>")
@auth_required
def edit_address(address_id):
    payload = request.get_json(silent=True) or {}
    result = update_address(g.user_id, address_id, payload)
    if not result:
        return error("Address not found", 404)
    return success(result, "Address updated")


@addresses_bp.delete("/<address_id>")
@auth_required
def remove_address(address_id):
    deleted = delete_address(g.user_id, address_id)
    if not deleted:
        return error("Address not found", 404)
    return success(None, "Address deleted")
