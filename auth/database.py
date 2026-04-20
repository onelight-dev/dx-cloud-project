import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv() #.env 파일로드

class Database:
    def __init__(self):
        self.config = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "database": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "cursor_factory": RealDictCursor
        }

    def insert_user(self, cognito_sub, email, name):
        # RETURNING id를 사용하여 생성된 UUID를 받아옵니다.
        query = """
            INSERT INTO users (id, cognito_sub, email, name, role, status, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, 'USER', 'ACTIVE', NOW(), NOW())
            RETURNING id
        """
        result = self.execute_commit_returning(query, (cognito_sub, email, name))
        return result['id'] # 생성된 UUID 반환
    
    # 단일 행 조회 메서스
    def execute_query_one(self, query, params=None):
        conn = psycopg2.connect(**self.config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(query, params)
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()

    # 조회 결과가 여러 줄이거나 없을 때 사용
    def execute_query(self, query, params=None):
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            conn.commit()  # 물리적으로 DB에 저장 (중요!)
            return True    # 성공 시 True 반환
        except Exception as e:
            conn.rollback() # 에러 발생 시 되돌리기
            raise e
        finally:
            cur.close()
            conn.close()

    def execute_commit_returning(self, query, params=None):
        # 연결 설정 (이미 클래스 내에 설정된 변수를 사용하세요)
        conn = psycopg2.connect(**self.config) 
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(query, params)
            # RETURNING 절에 의해 반환된 행을 가져옵니다.
            result = cur.fetchone() 
            conn.commit()
            return result # {'id': '...'} 형태의 딕셔너리를 반환합니다.
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    def get_or_create_wishlist(self, user_id):
        # 유저의 위시리스트가 있는지 확인하고 없으면 새로 만듭니다.
        query = "SELECT id FROM wishlists WHERE user_id = %s"
        wishlist = self.execute_query_one(query, (user_id,))
    
        if not wishlist:
            create_query = "INSERT INTO wishlists (id, user_id) VALUES (gen_random_uuid(), %s) RETURNING id"
            wishlist = self.execute_commit_returning(create_query, (user_id,))
        
        return wishlist
    
    def get_or_create_cart(self, user_id):
        # 유저의 장바구니가 있는지 확인하고 없으면 새로 만듭니다.
        query = "SELECT id FROM carts WHERE user_id = %s"
        cart = self.execute_query_one(query, (user_id,))
    
        if not cart:
            create_query = "INSERT INTO carts (id, user_id) VALUES (gen_random_uuid(), %s) RETURNING id"
            cart = self.execute_commit_returning(create_query, (user_id,))
        
        return cart
    
    def get_connection(self):
        """트랜잭션을 위해 직접 커넥션을 반환합니다."""
        return psycopg2.connect(**self.config)

    def execute_transaction(self, queries_with_params):
        """
        queries_with_params: [(query, params), (query, params), ...] 형태의 리스트
        """
        conn = self.get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            results = []
            for query, params in queries_with_params:
                cur.execute(query, params)
                if "RETURNING" in query.upper():
                    results.append(cur.fetchone())
            conn.commit()
            return results
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()
    
    