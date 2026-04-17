import os
import requests
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import Database
from dotenv import load_dotenv

load_dotenv()

orders_bp = Blueprint('orders', __name__)
db = Database()

# 인증 서비스의 주소 (로컬 테스트 시 5001 포트 가정)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:5001")

def verify_token_with_auth_service(auth_header):
    """인증 서비스에 토큰 검증을 요청하는 헬퍼 함수"""
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    try:
        # Auth 서비스의 /auth/verify 엔드포인트 호출
        response = requests.get(
            f"{AUTH_SERVICE_URL}/auth/verify",
            headers={"Authorization": auth_header},
            timeout=3  # 타임아웃 설정 (인프라 안정성)
        )
        if response.status_code == 200:
            return response.json().get("sub")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Auth Service Connection Error: {e}")
        return None

@orders_bp.route('', methods=['POST'])
def create_order():
    # 1. 인증 서버를 통한 토큰 검증
    auth_header = request.headers.get('Authorization')
    user_sub = verify_token_with_auth_service(auth_header)
    
    if not user_sub:
        return jsonify({"error": "인증에 실패했거나 인증 서버에 연결할 수 없습니다."}), 401

    # 2. DB 유저 ID 조회
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))
    if not user:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404
    
    user_id = user['id']
    data = request.json # address_id, memo 등 포함
    address_id = data.get('address_id') #Postman에서 보낸 주소 ID
    
    # 3. 주문 처리 트랜잭션 시작
    conn = db.get_connection()
    cur = conn.cursor()
    
    try:
        # 1. 배송지 상세 정보 조회 (orders 테이블에 스냅샷을 찍기 위함)
        cur.execute("""
            SELECT recipient, phone, zip_code, address1, address2 
            FROM user_addresses 
            WHERE id = %s AND user_id = %s
        """, (address_id, user_id))
        addr = cur.fetchone()
        
        if not addr:
            return jsonify({"error": "유효한 배송지 정보를 찾을 수 없습니다."}), 400

        # 2. 장바구니 및 가격 정보 조회 (할인가 우선 참조)
        cur.execute("""
            SELECT ci.sku_id, ps.product_id, ci.quantity, 
                   COALESCE(p.discount_price, p.base_price) as price,
                   p.name as product_name, ps.sku_code
            FROM cart_items ci
            JOIN product_skus ps ON ci.sku_id = ps.id
            JOIN products p ON ps.product_id = p.id
            JOIN carts c ON ci.cart_id = c.id
            WHERE c.user_id = %s
        """, (user_id,))
        items = cur.fetchall()

        if not items:
            return jsonify({"error": "장바구니가 비어 있습니다."}), 400

        total_amount = sum(item['price'] * item['quantity'] for item in items)
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # 3. 주문 생성 (address_id 대신 상세 주소 정보를 직접 입력)
        cur.execute("""
            INSERT INTO orders (
                id, order_number, user_id, status, total_amount, 
                discount_amount, shipping_fee, final_amount,
                recipient, phone, zip_code, address1, address2,
                user_memo, created_at
            ) VALUES (gen_random_uuid(), %s, %s, 'PENDING', %s, 0, 0, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        """, (
            order_number, user_id, total_amount, total_amount,
            addr['recipient'], addr['phone'], addr['zip_code'], 
            addr['address1'], addr['address2'], data.get('memo')
        ))
        
        order_id = cur.fetchone()['id']

        # D. 주문 상세 아이템 생성 (order_items 테이블)
        for item in items:
            # subtotal 계산 (단가 * 수량)
            subtotal = item['price'] * item['quantity']
            
            cur.execute("""
                INSERT INTO order_items (
                    id, 
                    order_id, 
                    product_id,    -- 필수 누락 항목
                    sku_id, 
                    product_name,  -- 필수 누락 항목
                    sku_code,      -- 필수 누락 항목
                    unit_price, 
                    quantity, 
                    subtotal       -- 필수 누락 항목
                ) VALUES (
                    gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                order_id, 
                item['product_id'], 
                item['sku_id'], 
                item['product_name'], 
                item['sku_code'], 
                item['price'],     
                item['quantity'], 
                subtotal
                ))

        # E. 장바구니 비우기
        cur.execute("DELETE FROM cart_items WHERE cart_id = (SELECT id FROM carts WHERE user_id = %s)", (user_id,))
        
        conn.commit()
        return jsonify({"message": "Order created successfully", "order_id": order_id}), 201

    except Exception as e:
        conn.rollback() # 오류 발생 시 모든 변경사항 되돌림
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@orders_bp.route('', methods=['GET'])
def get_my_orders():
    # 토큰 검증
    auth_header = request.headers.get('Authorization')
    user_sub = verify_token_with_auth_service(auth_header)
    if not user_sub:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))

    # 사용자의 주문 목록을 최신순으로 조회
    orders = db.execute_query("""
        SELECT id, order_number, status, total_amount, final_amount, created_at 
        FROM orders 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (user['id'],))
    
    return jsonify(orders), 200

@orders_bp.route('/<uuid:order_id>', methods=['GET'])
def get_order_detail(order_id):
    # 토큰 검증
    auth_header = request.headers.get('Authorization')
    user_sub = verify_token_with_auth_service(auth_header)
    if not user_sub:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))

    # 주문 기본 정보 조회
    order = db.execute_query_one("""
        SELECT * FROM orders WHERE id = %s
    """, (str(order_id),))
    
    if not order:
        return jsonify({"error": "주문을 찾을 수 없습니다."}), 404

    # 해당 주문에 속한 상세 아이템 조회
    items = db.execute_query_one("""
        SELECT product_name, sku_code, unit_price, quantity, subtotal 
        FROM order_items 
        WHERE order_id = %s
    """, (str(order_id),))
    
    order['items'] = items
    return jsonify(order), 200

@orders_bp.route('/<uuid:order_id>', methods=['PATCH'])
def update_order(order_id):
    # 토큰 검증
    auth_header = request.headers.get('Authorization')
    user_sub = verify_token_with_auth_service(auth_header)
    if not user_sub:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))

    data = request.json
    
    # 배송 시작 전(PENDING) 상태인지 확인 로직 권장
    # 수정 가능한 컬럼들 업데이트
    query = """
        UPDATE orders 
        SET recipient = COALESCE(%s, recipient),
            phone = COALESCE(%s, phone),
            zip_code = COALESCE(%s, zip_code),
            address1 = COALESCE(%s, address1),
            address2 = COALESCE(%s, address2),
            user_memo = COALESCE(%s, user_memo)
        WHERE id = %s
    """
    db.execute_query(query, (
        data.get('recipient'), data.get('phone'), data.get('zip_code'),
        data.get('address1'), data.get('address2'), data.get('memo'),
        str(order_id)
    ))
    
    return jsonify({"message": "주문 정보가 수정되었습니다."}), 200

@orders_bp.route('/<uuid:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    # 토큰 검증
    auth_header = request.headers.get('Authorization')
    user_sub = verify_token_with_auth_service(auth_header)
    if not user_sub:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))
    
    # 상태를 CANCELLED로 변경
    db.execute_query("""
        UPDATE orders 
        SET status = 'CANCELLED' 
        WHERE id = %s AND status = 'PENDING'
    """, (str(order_id), user['id']))
    
    return jsonify({"message": "주문이 취소되었습니다."}), 200