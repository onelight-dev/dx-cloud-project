from functools import wraps

from flask import request, g

from common.cognito import verify_cognito_token
from common.exceptions import UnauthorizedError


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            raise UnauthorizedError("로그인이 필요합니다.")

        token = auth_header.replace("Bearer ", "", 1).strip()
        if not token:
            raise UnauthorizedError("토큰이 없습니다.")

        claims = verify_cognito_token(token)

        g.cognito_claims = claims
        g.cognito_sub = claims.get("sub")
        g.email = claims.get("email")
        g.groups = claims.get("cognito:groups", [])

        return func(*args, **kwargs)

    return wrapper