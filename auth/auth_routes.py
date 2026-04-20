from flask import Blueprint, request, jsonify
from cognito_utils import CognitoWrapper
from database import Database

auth_bp = Blueprint('auth', __name__)

# 설정값 입력
cognito = CognitoWrapper("ap-northeast-2", "ap-northeast-2_o8WAIckGF", "5et3nig7v4s53uep0o85u7lduh", "e2rke9kufnh1p9ejct6aio6n1tchhn0284hnkkod7e7ssk0ovpf")
db = Database()

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.json
    try:
        # 1. Cognito 회원가입
        sub = cognito.sign_up(data['email'], data['password'], data['name'])
        
        # 2. DB에 유저 정보 저장 (이때 DB의 UUID가 생성됩니다)
        user_id = db.insert_user(sub, data['email'], data['name'])

        # 3. 해당유저의 장바구니와 위시리스트 생성
        db.get_or_create_wishlist(user_id)
        db.get_or_create_cart(user_id)

        return jsonify({"message": "Success", "sub": sub}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    try:
        result = cognito.login(data['email'], data['password'])
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    
# 1. 토큰 재발급 (POST /refresh)
@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    data = request.json
    refresh_token = data.get('refresh_token')
    user_identifier = data.get('sub')

    if not refresh_token or not user_identifier:
        return jsonify({"error": "refresh_token과 sub가 필요합니다."}), 400

    try:
        new_tokens = cognito.refresh_token(refresh_token, user_identifier)
        return jsonify(new_tokens), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 401

# 2. 로그아웃 (POST /logout)
@auth_bp.route('/logout', methods=['POST'])
def logout():
    # 보통 Authorization 헤더에 'Bearer <token>' 형태로 보냅니다.
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Access Token이 필요합니다."}), 400
    
    access_token = auth_header.split(' ')[1]
    
    try:
        cognito.logout(access_token)
        return jsonify({"message": "로그아웃 성공"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
# 다른 api가 토큰 유효성을 물어보는 엔드포인트
@auth_bp.route('/verify', methods=['GET'])
def verify_user():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "No token provided"}), 401
    
    token = auth_header.split(' ')[1]
    try:
        # cognito_utils를 사용하여 토큰 검증
        user_sub = cognito.verify_token(token)
        if user_sub:
            # 검증 성공 시 sub 반환
            return jsonify({"sub": user_sub}), 200
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 401