from database.db import get_db


ALLOWED_FIELDS = {
    "recipient_name",
    "phone",
    "zip_code",
    "address1",
    "address2",
    "is_default",
}


def list_addresses(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, recipient_name, phone, zip_code, address1, address2, is_default, created_at, updated_at
                FROM addresses
                WHERE user_id = %s
                ORDER BY is_default DESC, created_at DESC
                """,
                (user_id,),
            )
            return cur.fetchall()


def _clear_default_if_needed(conn, user_id: str, is_default: bool):
    if is_default:
        with conn.cursor() as cur:
            cur.execute("UPDATE addresses SET is_default = FALSE, updated_at = NOW() WHERE user_id = %s", (user_id,))


def create_address(user_id: str, payload: dict):
    with get_db() as conn:
        _clear_default_if_needed(conn, user_id, bool(payload.get("is_default")))
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO addresses (user_id, recipient_name, phone, zip_code, address1, address2, is_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, user_id, recipient_name, phone, zip_code, address1, address2, is_default, created_at, updated_at
                """,
                (
                    user_id,
                    payload["recipient_name"],
                    payload["phone"],
                    payload["zip_code"],
                    payload["address1"],
                    payload.get("address2"),
                    bool(payload.get("is_default", False)),
                ),
            )
            return cur.fetchone()


def update_address(user_id: str, address_id: str, payload: dict):
    updates = {k: v for k, v in payload.items() if k in ALLOWED_FIELDS}
    if not updates:
        raise ValueError("No updatable fields provided")

    with get_db() as conn:
        _clear_default_if_needed(conn, user_id, bool(updates.get("is_default")))
        set_clause = ", ".join([f"{field} = %s" for field in updates]) + ", updated_at = NOW()"
        values = list(updates.values()) + [user_id, address_id]

        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE addresses
                SET {set_clause}
                WHERE user_id = %s AND id = %s
                RETURNING id, user_id, recipient_name, phone, zip_code, address1, address2, is_default, created_at, updated_at
                """,
                values,
            )
            return cur.fetchone()


def delete_address(user_id: str, address_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM addresses WHERE user_id = %s AND id = %s RETURNING id", (user_id, address_id))
            return cur.fetchone() is not None
