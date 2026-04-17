from flask import Flask
from flask_cors import CORS
from auth_routes import auth_bp

app = Flask(__name__)
CORS(app)

# 인증 블루프린트만 등록
app.register_blueprint(auth_bp)

@app.route('/health')
def health_check():
    return {"status": "healthy", "service": "auth-service"}, 200

if __name__ == '__main__':
    # 인증 서비스는 보통 5001 포트 등 별도 포트 지정 가능
    app.run(host='0.0.0.0', port=5001, debug=True)