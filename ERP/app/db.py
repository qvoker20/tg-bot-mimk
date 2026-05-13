import psycopg2

from .config import PG_CONN


def get_db_connection():
    return psycopg2.connect(**PG_CONN)
