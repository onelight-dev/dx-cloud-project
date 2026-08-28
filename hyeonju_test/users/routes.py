from flask import Blueprint, jsonify, request

from users.service import (
    add_my_address,
    delete_my_address,
    get_me,
    get_my_addresses,
    update_me,
    update_my_address,
    withdraw_me,
)

user_bp = Blueprint("users", __name__)


@user_bp.get("/me")
def get_my_profile():
    return jsonify(get_me()), 200


@user_bp.patch("/me")
def patch_my_profile():
    payload = request.get_json(silent=True) or {}
    result = update_me(
        name=payload.get("name"),
        phone=payload.get("phone"),
    )
    return jsonify(result), 200


@user_bp.delete("/me")
def delete_my_profile():
    result = withdraw_me()
    return jsonify(result), 200


@user_bp.get("/me/addresses")
def get_my_address_list():
    return jsonify(get_my_addresses()), 200


@user_bp.post("/me/addresses")
def create_my_address():
    payload = request.get_json(silent=True) or {}

    required_fields = ["recipient", "phone", "zip_code", "address1"]
    for field in required_fields:
        if not payload.get(field):
            return jsonify({"error": f"{field}는 필수입니다."}), 400

    result = add_my_address(
        alias=payload.get("alias"),
        recipient=payload.get("recipient"),
        phone=payload.get("phone"),
        zip_code=payload.get("zip_code"),
        address1=payload.get("address1"),
        address2=payload.get("address2"),
        is_default=payload.get("is_default", False),
    )
    return jsonify(result), 201


@user_bp.patch("/me/addresses/<address_id>")
def patch_my_address(address_id):
    payload = request.get_json(silent=True) or {}

    result = update_my_address(
        address_id=address_id,
        alias=payload.get("alias"),
        recipient=payload.get("recipient"),
        phone=payload.get("phone"),
        zip_code=payload.get("zip_code"),
        address1=payload.get("address1"),
        address2=payload.get("address2"),
        is_default=payload.get("is_default"),
    )
    status_code = 200 if "error" not in result else 404
    return jsonify(result), status_code


@user_bp.delete("/me/addresses/<address_id>")
def remove_my_address(address_id):
    result = delete_my_address(address_id)
    status_code = 200 if "error" not in result else 404
    return jsonify(result), status_code