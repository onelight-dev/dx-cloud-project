import os
from flask import Flask, jsonify
from flask_cors import CORS
from auth_routes import auth_bp
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")
app.register_blueprint(auth_bp)

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method Not Allowed"}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal Server Error"}), 500

@app.route('/health')
def health_check():
    return {"status": "healthy", "service": "auth-service"}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5001)), debug=False)