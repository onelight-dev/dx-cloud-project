import os

import psycopg


def get_connection():
    host = os.getenv("DB_HOST", "211.46.52.153")
    port = int(os.getenv("DB_PORT", 15432))
    dbname = os.getenv("DB_NAME", "pg_local")
    user = os.getenv("DB_USER", "team3")
    password = os.getenv("DB_PASSWORD", "")

    print("### DB CONNECT ###", {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
    })

    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        autocommit=False,
    )