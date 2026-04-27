import atexit
import os
from flask import Flask, jsonify
from database import init_pool, close_pool
from routes.admin import bp as admin_bp


def create_app() -> Flask:
    app = Flask(__name__)
    init_pool()
    atexit.register(close_pool)

    app.register_blueprint(admin_bp)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "요청한 리소스를 찾을 수 없습니다."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "허용되지 않는 HTTP 메서드입니다."}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "서버 내부 오류가 발생했습니다."}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5010)), debug=False)
