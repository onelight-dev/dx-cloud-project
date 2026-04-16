from flask import Blueprint, jsonify, g

from common.decorators import login_required


auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/me", methods=["GET"])
@login_required
def auth_me():
    return jsonify({
        "message": "cognito token verified",
        "claims": g.cognito_claims
    }), 200