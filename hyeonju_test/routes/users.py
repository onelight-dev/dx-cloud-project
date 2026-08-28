from datetime import datetime

from flask import Blueprint, jsonify, request, g

from common.decorators import login_required
from common.exceptions import BadRequestError, NotFoundError
from extensions import db
from models.user import User
from models.address import Address


users_bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


def parse_birth_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise BadRequestError("birth_date 형식은 YYYY-MM-DD 이어야 합니다.")


def get_or_create_current_user():
    cognito_sub = g.cognito_sub
    email = g.email

    if not cognito_sub:
        raise BadRequestError("Cognito sub가 없습니다.")

    user = User.query.filter_by(cognito_sub=cognito_sub).first()
    if user:
        return user

    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            user.cognito_sub = cognito_sub
            db.session.commit()
            return user

    user_name = (
        g.cognito_claims.get("name")
        or g.cognito_claims.get("preferred_username")
        or email
        or "신규 사용자"
    )

    user = User(
        cognito_sub=cognito_sub,
        login_id=None,
        user_name=user_name,
        email=email or f"{cognito_sub}@local.user",
    )

    db.session.add(user)
    db.session.commit()
    return user


@users_bp.route("/sync", methods=["POST"])
@login_required
def sync_user():
    user = get_or_create_current_user()
    return jsonify({
        "message": "사용자 동기화 완료",
        "user": user.to_dict()
    }), 200


@users_bp.route("/me", methods=["GET"])
@login_required
def get_my_info():
    user = get_or_create_current_user()

    return jsonify({
        "user": user.to_dict()
    }), 200


@users_bp.route("/me", methods=["PATCH"])
@login_required
def update_my_info():
    user = get_or_create_current_user()
    data = request.get_json(silent=True) or {}

    user_name = data.get("user_name")
    phone = data.get("phone")
    birth_date_raw = data.get("birth_date")
    gender = data.get("gender")

    if user_name is not None:
        user_name = user_name.strip()
        if not user_name:
            raise BadRequestError("이름은 비워둘 수 없습니다.")
        user.user_name = user_name

    if phone is not None:
        user.phone = phone.strip() if phone else None

    if birth_date_raw is not None:
        birth_date_raw = birth_date_raw.strip() if birth_date_raw else ""
        user.birth_date = parse_birth_date(birth_date_raw)

    if gender is not None:
        user.gender = gender.strip() if gender else None

    db.session.commit()

    return jsonify({
        "message": "회원정보가 수정되었습니다.",
        "user": user.to_dict()
    }), 200


@users_bp.route("/me/addresses", methods=["GET"])
@login_required
def get_my_addresses():
    user = get_or_create_current_user()

    addresses = (
        Address.query
        .filter_by(user_id=user.user_id)
        .order_by(Address.is_default.desc(), Address.address_id.asc())
        .all()
    )

    return jsonify({
        "addresses": [address.to_dict() for address in addresses],
        "count": len(addresses)
    }), 200


@users_bp.route("/me/addresses", methods=["POST"])
@login_required
def create_address():
    user = get_or_create_current_user()
    data = request.get_json(silent=True) or {}

    recipient_name = (data.get("recipient_name") or "").strip()
    recipient_phone = (data.get("recipient_phone") or "").strip()
    zip_code = (data.get("zip_code") or "").strip()
    address1 = (data.get("address1") or "").strip()
    address2 = (data.get("address2") or "").strip() or None
    is_default = bool(data.get("is_default", False))
    delivery_request = (data.get("delivery_request") or "").strip() or None

    if not recipient_name:
        raise BadRequestError("수령인은 필수입니다.")
    if not recipient_phone:
        raise BadRequestError("연락처는 필수입니다.")
    if not zip_code:
        raise BadRequestError("우편번호는 필수입니다.")
    if not address1:
        raise BadRequestError("기본 주소는 필수입니다.")

    if is_default:
        Address.query.filter_by(user_id=user.user_id, is_default=True).update(
            {"is_default": False}
        )

    address = Address(
        user_id=user.user_id,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        zip_code=zip_code,
        address1=address1,
        address2=address2,
        is_default=is_default,
        delivery_request=delivery_request,
    )

    db.session.add(address)
    db.session.commit()

    return jsonify({
        "message": "배송지가 등록되었습니다.",
        "address": address.to_dict()
    }), 201


@users_bp.route("/me/addresses/<int:address_id>", methods=["PATCH"])
@login_required
def update_address(address_id: int):
    user = get_or_create_current_user()

    address = Address.query.filter_by(
        address_id=address_id,
        user_id=user.user_id
    ).first()

    if not address:
        raise NotFoundError("배송지를 찾을 수 없습니다.")

    data = request.get_json(silent=True) or {}

    if "recipient_name" in data:
        recipient_name = (data.get("recipient_name") or "").strip()
        if not recipient_name:
            raise BadRequestError("수령인은 비워둘 수 없습니다.")
        address.recipient_name = recipient_name

    if "recipient_phone" in data:
        recipient_phone = (data.get("recipient_phone") or "").strip()
        if not recipient_phone:
            raise BadRequestError("연락처는 비워둘 수 없습니다.")
        address.recipient_phone = recipient_phone

    if "zip_code" in data:
        zip_code = (data.get("zip_code") or "").strip()
        if not zip_code:
            raise BadRequestError("우편번호는 비워둘 수 없습니다.")
        address.zip_code = zip_code

    if "address1" in data:
        address1 = (data.get("address1") or "").strip()
        if not address1:
            raise BadRequestError("기본 주소는 비워둘 수 없습니다.")
        address.address1 = address1

    if "address2" in data:
        address.address2 = (data.get("address2") or "").strip() or None

    if "delivery_request" in data:
        address.delivery_request = (data.get("delivery_request") or "").strip() or None

    if "is_default" in data:
        is_default = bool(data.get("is_default"))
        if is_default:
            Address.query.filter_by(user_id=user.user_id, is_default=True).update(
                {"is_default": False}
            )
        address.is_default = is_default

    db.session.commit()

    return jsonify({
        "message": "배송지가 수정되었습니다.",
        "address": address.to_dict()
    }), 200


@users_bp.route("/me/addresses/<int:address_id>", methods=["DELETE"])
@login_required
def delete_address(address_id: int):
    user = get_or_create_current_user()

    address = Address.query.filter_by(
        address_id=address_id,
        user_id=user.user_id
    ).first()

    if not address:
        raise NotFoundError("배송지를 찾을 수 없습니다.")

    was_default = address.is_default

    db.session.delete(address)
    db.session.commit()

    if was_default:
        next_address = (
            Address.query
            .filter_by(user_id=user.user_id)
            .order_by(Address.address_id.asc())
            .first()
        )
        if next_address:
            next_address.is_default = True
            db.session.commit()

    return jsonify({
        "message": "배송지가 삭제되었습니다."
    }), 200