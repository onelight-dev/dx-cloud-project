import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "ecommerce"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", 1))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", 10))
