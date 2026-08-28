import time
import requests
import jwt

from flask import current_app

from common.exceptions import UnauthorizedError


_jwks_cache = {
    "keys": None,
    "expires_at": 0,
}


def _get_jwks_url() -> str:
    region = current_app.config["COGNITO_REGION"]
    user_pool_id = current_app.config["COGNITO_USER_POOL_ID"]
    return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"


def _get_issuer() -> str:
    region = current_app.config["COGNITO_REGION"]
    user_pool_id = current_app.config["COGNITO_USER_POOL_ID"]
    return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"


def _get_jwks():
    now = time.time()

    if _jwks_cache["keys"] and _jwks_cache["expires_at"] > now:
        return _jwks_cache["keys"]

    response = requests.get(_get_jwks_url(), timeout=5)
    response.raise_for_status()

    jwks = response.json()
    _jwks_cache["keys"] = jwks["keys"]
    _jwks_cache["expires_at"] = now + 3600
    return jwks["keys"]


def verify_cognito_token(token: str) -> dict:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise UnauthorizedError("유효하지 않은 토큰 형식입니다.")

    kid = unverified_header.get("kid")
    if not kid:
        raise UnauthorizedError("토큰 kid가 없습니다.")

    keys = _get_jwks()
    public_key = None

    for key in keys:
        if key["kid"] == kid:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            break

    if public_key is None:
        raise UnauthorizedError("일치하는 공개키를 찾을 수 없습니다.")

    try:
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=current_app.config["COGNITO_APP_CLIENT_ID"],
            issuer=_get_issuer(),
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("유효하지 않은 토큰입니다.")