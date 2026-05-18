import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

from .config import PG_CONN

# Global connection pool (initialized at startup, cleaned at shutdown)
_connection_pool = None

# For development: disable pooling if DEV_MODE=1
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"


def initialize_connection_pool(minconn: int = 5, maxconn: int = 20) -> None:
    """Initialize the global database connection pool.
    
    Call this on application startup.
    minconn: minimum number of idle connections to keep in pool
    maxconn: maximum number of connections the pool will create
    
    If DEV_MODE=1, pooling is disabled and direct connections are used.
    """
    global _connection_pool
    if DEV_MODE:
        _connection_pool = None
        return
    
    if _connection_pool is None:
        _connection_pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            **PG_CONN
        )


@contextmanager
def get_db_connection():
    """Get a connection from the pool (context manager).
    
    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(...)
    """
    global _connection_pool
    
    if DEV_MODE or _connection_pool is None:
        # Direct connection without pooling (for development)
        conn = psycopg2.connect(**PG_CONN)
        try:
            yield conn
        finally:
            conn.close()
    else:
        # Get connection from pool
        conn = _connection_pool.getconn()
        try:
            yield conn
        finally:
            _connection_pool.putconn(conn)


def return_db_connection(conn):
    """Legacy function for backwards compatibility. Not needed with context manager."""
    global _connection_pool
    if _connection_pool is not None and conn is not None:
        _connection_pool.putconn(conn)


def close_connection_pool() -> None:
    """Close all connections in the pool. Call on application shutdown."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None

