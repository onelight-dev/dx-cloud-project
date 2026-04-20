from datetime import datetime

from extensions import db


class Address(db.Model):
    __tablename__ = "addresses"

    address_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_name = db.Column(db.String(100), nullable=False)
    recipient_phone = db.Column(db.String(20), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    address1 = db.Column(db.String(255), nullable=False)
    address2 = db.Column(db.String(255), nullable=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    delivery_request = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("addresses", lazy=True))

    def to_dict(self) -> dict:
        return {
            "address_id": self.address_id,
            "user_id": self.user_id,
            "recipient_name": self.recipient_name,
            "recipient_phone": self.recipient_phone,
            "zip_code": self.zip_code,
            "address1": self.address1,
            "address2": self.address2,
            "is_default": self.is_default,
            "delivery_request": self.delivery_request,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }