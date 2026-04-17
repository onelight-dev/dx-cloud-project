from functools import wraps
from flask import g, request
import jwt
from common.cognito import decode_token
from common.responses import error


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return error("Authorization header is required", 401, code="AUTH_HEADER_MISSING")

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return error("Token is missing", 401, code="TOKEN_MISSING")

        try:
            payload = decode_token(token)
            g.user_id = payload["sub"]
            g.user_email = payload.get("email")
            g.user_role = payload.get("role", "user")
        except jwt.ExpiredSignatureError:
            return error("Token expired", 401, code="TOKEN_EXPIRED")
        except jwt.InvalidTokenError:
            return error("Invalid token", 401, code="INVALID_TOKEN")

        return fn(*args, **kwargs)

    return wrapper
