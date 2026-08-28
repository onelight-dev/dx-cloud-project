from flask import jsonify

from common.exceptions import ApiError


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({
            "error": {
                "code": error.code,
                "message": error.message,
            }
        }), error.status_code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        return jsonify({
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(error),
            }
        }), 500
