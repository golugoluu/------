import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    conn = psycopg2.connect(
        host='localhost',
        database='fruit_sale_system',
        user='pass',
        password='pass',
        client_encoding='UTF8'
    )
    return conn