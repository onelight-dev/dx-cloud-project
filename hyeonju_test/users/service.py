from uuid import uuid4

from psycopg.rows import dict_row

from database.db import get_connection

print("### DB USER SERVICE LOADED ###")

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_COGNITO_SUB = "test-cognito-sub"
TEST_EMAIL = "test@test.com"


def ensure_test_user():
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # 1) id로 먼저 찾기
            cur.execute(
                """
                SELECT id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                FROM users
                WHERE id = %s
                """,
                (TEST_USER_ID,),
            )
            existing = cur.fetchone()

            if existing:
                print("### TEST USER EXISTS BY ID ###", existing["id"])
                return existing

            # 2) email 또는 cognito_sub 로 기존 유저 찾기
            cur.execute(
                """
                SELECT id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                FROM users
                WHERE email = %s OR cognito_sub = %s
                LIMIT 1
                """,
                (TEST_EMAIL, TEST_COGNITO_SUB),
            )
            existing = cur.fetchone()

            if existing:
                print("### TEST USER EXISTS BY EMAIL OR COGNITO_SUB ###", existing["id"])

                # 기존 유저를 테스트 유저 값으로 맞춰줌
                cur.execute(
                    """
                    UPDATE users
                    SET
                        cognito_sub = %s,
                        email = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                    """,
                    (TEST_COGNITO_SUB, TEST_EMAIL, existing["id"]),
                )
                updated = cur.fetchone()
                conn.commit()
                print("### TEST USER REUSED + COMMIT ###", updated["id"])
                return updated

            # 3) 없으면 새로 생성
            cur.execute(
                """
                INSERT INTO users (
                    id, cognito_sub, email, name, phone, role, status,
                    default_address_id, withdrawn_at, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, 'USER', 'ACTIVE',
                    NULL, NULL, NOW(), NOW()
                )
                RETURNING id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                """,
                (
                    TEST_USER_ID,
                    TEST_COGNITO_SUB,
                    TEST_EMAIL,
                    "테스트유저",
                    "010-1234-5678",
                ),
            )
            created = cur.fetchone()
            conn.commit()
            print("### TEST USER CREATED + COMMIT ###", created["id"])
            return created


def get_me():
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                FROM users
                WHERE id = %s
                """,
                (user["id"],),
            )
            user = cur.fetchone()
            print("### GET ME ###", user)
            return user


def update_me(name=None, phone=None):
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### UPDATE ME INPUT ###", {"name": name, "phone": phone, "user_id": user["id"]})

            cur.execute(
                """
                UPDATE users
                SET
                    name = COALESCE(%s, name),
                    phone = COALESCE(%s, phone),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                """,
                (name, phone, user["id"]),
            )
            updated_user = cur.fetchone()
            conn.commit()

            print("### UPDATE ME COMMIT ###", updated_user)

    return {
        "message": "프로필이 수정되었습니다.",
        "user": updated_user,
    }


def withdraw_me():
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE users
                SET
                    status = 'WITHDRAWN',
                    withdrawn_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, email, name, phone, role, status, default_address_id, withdrawn_at, created_at, updated_at
                """,
                (user["id"],),
            )
            updated_user = cur.fetchone()
            conn.commit()

            print("### WITHDRAW COMMIT ###", updated_user)

    return {
        "message": "회원 탈퇴가 완료되었습니다.",
        "user": updated_user,
    }


def get_my_addresses():
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, alias, recipient, phone, zip_code, address1, address2, is_default
                FROM user_addresses
                WHERE user_id = %s
                ORDER BY is_default DESC, id ASC
                """,
                (user["id"],),
            )
            items = cur.fetchall()
            print("### GET ADDRESSES ###", items)

    return {"items": items}


def add_my_address(alias, recipient, phone, zip_code, address1, address2, is_default=False):
    user = ensure_test_user()
    address_id = str(uuid4())

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### ADD ADDRESS INPUT ###", {
                "address_id": address_id,
                "user_id": user["id"],
                "alias": alias,
                "recipient": recipient,
                "phone": phone,
                "zip_code": zip_code,
                "address1": address1,
                "address2": address2,
                "is_default": is_default,
            })

            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM user_addresses
                WHERE user_id = %s
                """,
                (user["id"],),
            )
            row = cur.fetchone()
            has_no_address = row["cnt"] == 0
            should_default = bool(is_default) or has_no_address

            if should_default:
                cur.execute(
                    """
                    UPDATE user_addresses
                    SET is_default = FALSE
                    WHERE user_id = %s
                    """,
                    (user["id"],),
                )

            cur.execute(
                """
                INSERT INTO user_addresses (
                    id, user_id, alias, recipient, phone, zip_code, address1, address2, is_default
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, alias, recipient, phone, zip_code, address1, address2, is_default
                """,
                (
                    address_id,
                    user["id"],
                    alias,
                    recipient,
                    phone,
                    zip_code,
                    address1,
                    address2,
                    should_default,
                ),
            )
            new_address = cur.fetchone()

            if should_default:
                cur.execute(
                    """
                    UPDATE users
                    SET default_address_id = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (address_id, user["id"]),
                )

            conn.commit()
            print("### ADD ADDRESS COMMIT ###", new_address)

    return {
        "message": "배송지가 등록되었습니다.",
        "address": new_address,
    }


def update_my_address(address_id, alias=None, recipient=None, phone=None, zip_code=None, address1=None, address2=None, is_default=None):
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### UPDATE ADDRESS INPUT ###", {
                "address_id": address_id,
                "user_id": user["id"],
                "alias": alias,
                "recipient": recipient,
                "phone": phone,
                "zip_code": zip_code,
                "address1": address1,
                "address2": address2,
                "is_default": is_default,
            })

            cur.execute(
                """
                SELECT id, alias, recipient, phone, zip_code, address1, address2, is_default
                FROM user_addresses
                WHERE id = %s AND user_id = %s
                """,
                (address_id, user["id"]),
            )
            existing = cur.fetchone()

            if not existing:
                print("### UPDATE ADDRESS NOT FOUND ###", address_id)
                return {"error": "배송지를 찾을 수 없습니다."}

            cur.execute(
                """
                UPDATE user_addresses
                SET
                    alias = COALESCE(%s, alias),
                    recipient = COALESCE(%s, recipient),
                    phone = COALESCE(%s, phone),
                    zip_code = COALESCE(%s, zip_code),
                    address1 = COALESCE(%s, address1),
                    address2 = COALESCE(%s, address2)
                WHERE id = %s AND user_id = %s
                """,
                (
                    alias,
                    recipient,
                    phone,
                    zip_code,
                    address1,
                    address2,
                    address_id,
                    user["id"],
                ),
            )

            if is_default is True:
                cur.execute(
                    """
                    UPDATE user_addresses
                    SET is_default = FALSE
                    WHERE user_id = %s
                    """,
                    (user["id"],),
                )
                cur.execute(
                    """
                    UPDATE user_addresses
                    SET is_default = TRUE
                    WHERE id = %s AND user_id = %s
                    """,
                    (address_id, user["id"]),
                )
                cur.execute(
                    """
                    UPDATE users
                    SET default_address_id = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (address_id, user["id"]),
                )

            cur.execute(
                """
                SELECT id, alias, recipient, phone, zip_code, address1, address2, is_default
                FROM user_addresses
                WHERE id = %s AND user_id = %s
                """,
                (address_id, user["id"]),
            )
            updated_address = cur.fetchone()

            conn.commit()
            print("### UPDATE ADDRESS COMMIT ###", updated_address)

    return {
        "message": "배송지가 수정되었습니다.",
        "address": updated_address,
    }


def delete_my_address(address_id):
    user = ensure_test_user()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            print("### DELETE ADDRESS INPUT ###", {"address_id": address_id, "user_id": user["id"]})

            cur.execute(
                """
                SELECT id, is_default
                FROM user_addresses
                WHERE id = %s AND user_id = %s
                """,
                (address_id, user["id"]),
            )
            existing = cur.fetchone()

            if not existing:
                print("### DELETE ADDRESS NOT FOUND ###", address_id)
                return {"error": "배송지를 찾을 수 없습니다."}

            was_default = existing["is_default"]

            cur.execute(
                """
                DELETE FROM user_addresses
                WHERE id = %s AND user_id = %s
                """,
                (address_id, user["id"]),
            )

            if was_default:
                cur.execute(
                    """
                    SELECT id
                    FROM user_addresses
                    WHERE user_id = %s
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (user["id"],),
                )
                next_default = cur.fetchone()

                if next_default:
                    next_default_id = next_default["id"]

                    cur.execute(
                        """
                        UPDATE user_addresses
                        SET is_default = TRUE
                        WHERE id = %s
                        """,
                        (next_default_id,),
                    )
                    cur.execute(
                        """
                        UPDATE users
                        SET default_address_id = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (next_default_id, user["id"]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE users
                        SET default_address_id = NULL, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (user["id"],),
                    )

            conn.commit()
            print("### DELETE ADDRESS COMMIT ###", address_id)

    return {"message": "배송지가 삭제되었습니다."}