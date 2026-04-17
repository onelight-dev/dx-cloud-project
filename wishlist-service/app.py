from flask import Flask
from config import Config
from extensions import cors
from routes.wishlist import wishlist_bp
from common.responses import error


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    cors.init_app(app)

    app.register_blueprint(wishlist_bp, url_prefix="/wishlist")

    @app.get("/health")
    def health():
        return {"service": app.config["SERVICE_NAME"], "status": "ok"}

    @app.errorhandler(ValueError)
    def handle_value_error(exc):
        return error(str(exc), 400)

    @app.errorhandler(Exception)
    def handle_exception(exc):
        app.logger.exception(exc)
        return error("Internal server error", 500, code="INTERNAL_SERVER_ERROR")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"])
