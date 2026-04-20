import os
from dotenv import load_dotenv
import boto3
import hmac
import hashlib
import base64
from botocore.exceptions import ClientError

load_dotenv()

class CognitoWrapper:
    def __init__(self, region, user_pool_id, client_id, client_secret):
        self.region = os.getenv("COGNITO_REGION")
        self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
        self.client_id = os.getenv("COGNITO_CLIENT_ID")
        self.client_secret = os.getenv("COGNITO_CLIENT_SECRET")
        self.client = boto3.client('cognito-idp', region_name=self.region)

    def get_secret_hash(self, username):
        # Secret Hash 계산 공식: HMAC_SHA256(client_secret, username + client_id)
        msg = username + self.client_id
        dig = hmac.new(
            str(self.client_secret).encode('utf-8'),
            msg.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(dig).decode()

    def sign_up(self, email, password, name):
        try:
            secret_hash = self.get_secret_hash(email)
            response = self.client.sign_up(
                ClientId=self.client_id,
                SecretHash=secret_hash, # SecretHash 추가
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'name', 'Value': name}
                ]
            )
            return response['UserSub']
        except ClientError as e:
            raise Exception(e.response['Error']['Message'])

    def login(self, email, password):
        try:
            secret_hash = self.get_secret_hash(email)
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password,
                    'SECRET_HASH': secret_hash # SecretHash 추가
                }
            )
            return response['AuthenticationResult']
        except ClientError as e:
            raise Exception(e.response['Error']['Message'])
        
    def refresh_token(self, refresh_token, sub):
        try:
            # Refresh 토큰 흐름에서도 SecretHash가 필요합니다.
            secret_hash = self.get_secret_hash(sub)

            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH', # 리프레시 흐름
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token,
                    'SECRET_HASH': secret_hash,
                    'USERNAME': sub
                }
            )
            # 새로운 AccessToken과 IdToken이 담긴 결과를 반환합니다.
            return response['AuthenticationResult']
        except ClientError as e:
            # 디버깅을 위해 로그를 찍어보는 것이 좋습니다.
            print(f"Cognito Refresh Error: {e.response['Error']['Message']}")
            raise Exception(e.response['Error']['Message'])

    def logout(self, access_token):
        try:
            # 해당 Access Token을 가진 유저의 모든 기기에서 로그아웃 처리
            self.client.global_sign_out(AccessToken=access_token)
            return True
        except ClientError as e:
            raise Exception(e.response['Error']['Message'])
        
    def verify_token(self, token):
        """액세스 토큰의 유효성을 검사하고 sub를 반환합니다."""
        try:
            # Cognito의 get_user는 토큰이 만료되었거나 조작된 경우 에러를 발생시킵니다.
            response = self.client.get_user(AccessToken=token)
            
            # 사용자 속성 중 'sub' (Cognito 고유 ID) 추출
            user_sub = next(attr['Value'] for attr in response['UserAttributes'] if attr['Name'] == 'sub')
            return user_sub
        except ClientError as e:
            print(f"Token verification failed: {e.response['Error']['Message']}")
            return None