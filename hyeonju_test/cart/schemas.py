from uuid import UUID

from common.exceptions import BadRequestError


def _require_uuid(value: str, field_name: str) -> str:
    try:
        UUID(str(value))
        return str(value)
    except Exception as exc:
        raise BadRequestError(f"{field_name}는 UUID 형식이어야 합니다.") from exc


def _require_positive_int(value, field_name: str) -> int:
    if not isinstance(value, int):
        raise BadRequestError(f"{field_name}는 정수여야 합니다.")
    if value <= 0:
        raise BadRequestError(f"{field_name}는 1 이상이어야 합니다.")
    return value


def validate_add_cart_item_payload(payload: dict) -> dict:
    product_id = _require_uuid(payload.get("product_id"), "product_id")
    sku_id = _require_uuid(payload.get("sku_id"), "sku_id")
    quantity = _require_positive_int(payload.get("quantity"), "quantity")

    return {
        "product_id": product_id,
        "sku_id": sku_id,
        "quantity": quantity,
    }


def validate_update_cart_item_payload(payload: dict) -> dict:
    if "quantity" not in payload and "sku_id" not in payload:
        raise BadRequestError("quantity 또는 sku_id 중 하나는 필요합니다.")

    validated = {}

    if "quantity" in payload:
        validated["quantity"] = _require_positive_int(payload.get("quantity"), "quantity")

    if "sku_id" in payload:
        validated["sku_id"] = _require_uuid(payload.get("sku_id"), "sku_id")

    return validated
