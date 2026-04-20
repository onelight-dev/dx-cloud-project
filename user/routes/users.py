from flask import Blueprint, request, g
from common.decorators import auth_required
from common.responses import success, error
from services.user_service import get_user_profile, update_user_profile, soft_delete_user

users_bp = Blueprint("users", __name__)


@users_bp.get("/me")
@auth_required
def get_profile():
    profile = get_user_profile(g.user_id)
    if not profile:
        return error("User not found", 404)
    return success(profile)


@users_bp.put("/me")
@auth_required
def update_profile():
    payload = request.get_json(silent=True) or {}
    updated = update_user_profile(g.user_id, payload)
    if not updated:
        return error("User not found", 404)
    return success(updated, "Profile updated")


@users_bp.delete("/me")
@auth_required
def delete_profile():
    deleted = soft_delete_user(g.user_id)
    if not deleted:
        return error("User not found", 404)
    return success(None, "User deleted")
