from database.db import get_db


ALLOWED_FIELDS = {"name", "phone", "birth_date", "gender"}


def get_user_profile(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, name, phone, birth_date, gender, created_at, updated_at
                FROM users
                WHERE id = %s AND deleted_at IS NULL
                """,
                (user_id,),
            )
            return cur.fetchone()


def update_user_profile(user_id: str, payload: dict):
    updates = {k: v for k, v in payload.items() if k in ALLOWED_FIELDS}
    if not updates:
        raise ValueError("No updatable fields provided")

    set_clause = ", ".join([f"{field} = %s" for field in updates]) + ", updated_at = NOW()"
    values = list(updates.values()) + [user_id]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users
                SET {set_clause}
                WHERE id = %s AND deleted_at IS NULL
                RETURNING id, email, name, phone, birth_date, gender, created_at, updated_at
                """,
                values,
            )
            return cur.fetchone()


def soft_delete_user(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s AND deleted_at IS NULL RETURNING id",
                (user_id,),
            )
            return cur.fetchone() is not None
