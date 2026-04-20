from flask import jsonify


def success(data=None, message="success", status=200):
    return jsonify({
        "success": True,
        "message": message,
        "data": data,
    }), status


def error(message="error", status=400, code=None):
    payload = {
        "success": False,
        "message": message,
    }
    if code:
        payload["code"] = code
    return jsonify(payload), status
