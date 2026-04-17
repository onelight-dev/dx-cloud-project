from flask import Flask
from flask_cors import CORS
from order_routes import orders_bp

app = Flask(__name__)
CORS(app)

# 주문 블루프린트만 등록 (url_prefix 유지)
app.register_blueprint(orders_bp, url_prefix='/orders')

@app.route('/health')
def health_check():
    return {"status": "healthy", "service": "order-service"}, 200

if __name__ == '__main__':
    # 주문 서비스 파드 실행
    app.run(host='0.0.0.0', port=5002, debug=True)