from functools import wraps

from flask import request

from common.exceptions import UnauthorizedError


TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id = request.headers.get("X-USER-ID")

        # 브라우저에서 직접 접근할 때 테스트용 사용자 강제 주입
        if not user_id:
            user_id = TEST_USER_ID

        if not user_id:
            raise UnauthorizedError("로그인이 필요합니다.")

        request.user_id = user_id
        return func(*args, **kwargs)

    return wrapper