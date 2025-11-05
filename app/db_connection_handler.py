"""
Database Connection Handler with SSL Error Recovery
Handles PostgreSQL SSL connection issues on Render
"""

import time
import logging
from functools import wraps
from sqlalchemy.exc import OperationalError, DisconnectionError
from psycopg2 import OperationalError as Psycopg2OperationalError
from flask import current_app

logger = logging.getLogger(__name__)

def db_retry_on_ssl_error(max_retries=3, delay=1.0, backoff=2.0):
    """
    Decorator to retry database operations on SSL connection errors
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (OperationalError, Psycopg2OperationalError, DisconnectionError) as e:
                    error_msg = str(e).lower()
                    
                    # Check if it's an SSL-related error
                    ssl_errors = [
                        'ssl connection has been closed unexpectedly',
                        'connection closed',
                        'server closed the connection unexpectedly',
                        'ssl error',
                        'connection reset',
                        'bad file descriptor'
                    ]
                    
                    is_ssl_error = any(ssl_err in error_msg for ssl_err in ssl_errors)
                    
                    if is_ssl_error and retries < max_retries - 1:
                        retries += 1
                        wait_time = delay * (backoff ** (retries - 1))
                        logger.warning(f"SSL connection error (attempt {retries}/{max_retries}): {e}")
                        logger.info(f"Retrying in {wait_time:.1f} seconds...")
                        time.sleep(wait_time)
                        
                        # Try to refresh the database connection
                        try:
                            from app import db
                            db.session.rollback()
                            db.engine.dispose()  # Force connection pool refresh
                        except Exception as refresh_error:
                            logger.warning(f"Could not refresh connection pool: {refresh_error}")
                        
                        continue
                    else:
                        # Re-raise the error if it's not SSL-related or max retries reached
                        logger.error(f"Database operation failed after {retries + 1} attempts: {e}")
                        raise
                except Exception as e:
                    # Non-connection related errors should be raised immediately
                    logger.error(f"Non-connection database error: {e}")
                    raise
            
            return None  # Should never reach here
        return wrapper
    return decorator

def safe_db_operation(operation_func, *args, **kwargs):
    """
    Execute a database operation with SSL error handling
    """
    @db_retry_on_ssl_error(max_retries=3, delay=1.0, backoff=2.0)
    def _execute():
        return operation_func(*args, **kwargs)
    
    return _execute()

def check_db_connection():
    """
    Check if database connection is healthy
    """
    try:
        from app import db
        from sqlalchemy import text
        
        # Simple connection test
        result = db.session.execute(text("SELECT 1")).scalar()
        return result == 1
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False

def refresh_db_connection():
    """
    Force refresh of database connection pool
    """
    try:
        from app import db
        logger.info("Refreshing database connection pool...")
        
        # Close all connections and recreate pool
        db.session.close()
        db.engine.dispose()
        
        # Test new connection
        from sqlalchemy import text
        db.session.execute(text("SELECT 1")).scalar()
        
        logger.info("Database connection pool refreshed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh database connection pool: {e}")
        return False

class DatabaseConnectionManager:
    """
    Context manager for database operations with SSL error handling
    """
    
    def __init__(self, auto_retry=True, max_retries=3):
        self.auto_retry = auto_retry
        self.max_retries = max_retries
        self.retries = 0
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and issubclass(exc_type, (OperationalError, Psycopg2OperationalError, DisconnectionError)):
            error_msg = str(exc_val).lower()
            ssl_errors = [
                'ssl connection has been closed unexpectedly',
                'connection closed',
                'server closed the connection unexpectedly'
            ]
            
            is_ssl_error = any(ssl_err in error_msg for ssl_err in ssl_errors)
            
            if is_ssl_error and self.auto_retry and self.retries < self.max_retries:
                logger.warning(f"SSL error in context manager: {exc_val}")
                refresh_db_connection()
                return True  # Suppress the exception
        
        return False  # Let other exceptions propagate
    
    def execute_with_retry(self, operation_func, *args, **kwargs):
        """
        Execute a database operation with retry logic
        """
        return safe_db_operation(operation_func, *args, **kwargs)

# Convenience functions for common database operations
def safe_query(query_func, *args, **kwargs):
    """Execute a query with SSL error handling"""
    return safe_db_operation(query_func, *args, **kwargs)

def safe_commit():
    """Commit with SSL error handling"""
    @db_retry_on_ssl_error()
    def _commit():
        from app import db
        db.session.commit()
    
    return _commit()

def safe_rollback():
    """Rollback with error handling"""
    try:
        from app import db
        db.session.rollback()
    except Exception as e:
        logger.warning(f"Rollback failed: {e}")
        # Try to refresh connection if rollback fails
        refresh_db_connection()
