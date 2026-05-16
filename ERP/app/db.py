import psycopg2
from psycopg2 import pool

from .config import PG_CONN

# Global connection pool (initialized at startup, cleaned at shutdown)
_connection_pool = None


def initialize_connection_pool(minconn: int = 5, maxconn: int = 20) -> None:
    """Initialize the global database connection pool.
    
    Call this on application startup.
    minconn: minimum number of idle connections to keep in pool
    maxconn: maximum number of connections the pool will create
    """
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            **PG_CONN
        )


def get_db_connection():
    """Get a connection from the pool."""
    global _connection_pool
    if _connection_pool is None:
        initialize_connection_pool()
    return _connection_pool.getconn()


def return_db_connection(conn):
    """Return a connection to the pool."""
    global _connection_pool
    if _connection_pool is not None and conn is not None:
        _connection_pool.putconn(conn)


def close_connection_pool() -> None:
    """Close all connections in the pool. Call on application shutdown."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None

