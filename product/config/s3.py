import os
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET_NAME  = os.environ["S3_BUCKET_NAME"]
S3_REGION       = os.getenv("S3_REGION", "ap-northeast-2")
S3_PUBLIC_URL   = os.getenv("S3_PUBLIC_URL", "").rstrip("/")

# MinIO 로컬 전용 — EKS 배포 시 미설정 (IAM Role 자동 사용)
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY   = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY   = os.getenv("S3_SECRET_KEY", "")
