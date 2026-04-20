import os
from dotenv import load_dotenv

load_dotenv()

SFTP_CONFIG = {
    "host":     os.getenv("SFTP_HOST", "localhost"),
    "port":     int(os.getenv("SFTP_PORT", 22)),
    "username": os.getenv("SFTP_USER", ""),
    "password": os.getenv("SFTP_PASSWORD", ""),
}

SFTP_BASE_DIR = os.getenv("SFTP_BASE_DIR", "/uploads/products")
SFTP_BASE_URL = os.getenv("SFTP_BASE_URL", "")   # 이미지 공개 URL 접두사 (e.g. https://cdn.example.com)
