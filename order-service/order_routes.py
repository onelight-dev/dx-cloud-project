from flask import Blueprint, request, jsonify
from database import Database
from cognito_utils import CognitoWrapper

import uuid
from datetime import datetime

orders_bp = Blueprint('orders', __name__)
db = Database()
cognito = CognitoWrapper("ap-northeast-2", "ap-northeast-2_o8WAIckGF", "5et3nig7v4s53uep0o85u7lduh", "e2rke9kufnh1p9ejct6aio6n1tchhn0284hnkkod7e7ssk0ovpf")

@orders_bp.route('', methods=['POST'])
def create_order():
    # 1. 토큰 검증 및 보안 처리
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "인증 토큰이 필요합니다."}), 401
    
    token = auth_header.split(' ')[1]
    user_sub = cognito.verify_token(token)
    
    if not user_sub:
        return jsonify({"error": "유효하지 않은 토큰입니다."}), 401

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
    # 토큰 검증 로직 (공통)
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    user_sub = cognito.verify_token(token)
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
    # 토큰 검증 로직 (공통)
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    user_sub = cognito.verify_token(token)
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
    # 토큰 검증 로직 (공통)
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    user_sub = cognito.verify_token(token)
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
    # 토큰 검증 로직 (공통)
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    user_sub = cognito.verify_token(token)
    user = db.execute_query_one("SELECT id FROM users WHERE cognito_sub = %s", (user_sub,))
    
    # 상태를 CANCELLED로 변경
    db.execute_query("""
        UPDATE orders 
        SET status = 'CANCELLED' 
        WHERE id = %s AND status = 'PENDING'
    """, (str(order_id), user['id']))
    
    return jsonify({"message": "주문이 취소되었습니다."}), 200