from flask import Flask, jsonify

from config import Config
from extensions import db
from routes.auth import auth_bp
from routes.users import users_bp
from common.exceptions import ApiError


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"message": "server is running"}), 200

    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return jsonify({
            "message": error.message
        }), error.status_code

    @app.errorhandler(404)
    def handle_404(_error):
        return jsonify({
            "message": "존재하지 않는 API입니다."
        }), 404

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)