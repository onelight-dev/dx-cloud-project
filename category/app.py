import atexit
from flask import Flask, jsonify
from database import init_pool, close_pool
from routes.category import bp as category_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # DB 커넥션 풀 초기화 (앱 시작 시 1회)
    init_pool()
    # 프로세스 종료 시 풀을 닫음 (요청마다 닫히지 않도록 atexit 사용)
    atexit.register(close_pool)

    # 블루프린트 등록
    app.register_blueprint(category_bp)

    # 전역 에러 핸들러
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
    app.run(debug=True, host="0.0.0.0", port=5001)
