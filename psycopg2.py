"""
Compatibility module to map psycopg2 imports to psycopg (v3)
This allows libraries that expect psycopg2 to work with psycopg
"""

try:
    # Try to import the real psycopg2 first
    from psycopg2 import *
    from psycopg2 import extras, extensions, pool, sql
except ImportError:
    # Fallback to psycopg (v3) with compatibility mapping
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    
    # Map psycopg2 functions to psycopg equivalents
    connect = psycopg.connect
    
    # Create compatibility classes and functions
    class extras:
        @staticmethod
        def RealDictCursor():
            return dict_row
        
        @staticmethod
        def DictCursor():
            return dict_row
    
    class extensions:
        ISOLATION_LEVEL_AUTOCOMMIT = psycopg.IsolationLevel.AUTOCOMMIT
        ISOLATION_LEVEL_READ_COMMITTED = psycopg.IsolationLevel.READ_COMMITTED
        ISOLATION_LEVEL_SERIALIZABLE = psycopg.IsolationLevel.SERIALIZABLE
        
        @staticmethod
        def set_isolation_level(conn, level):
            conn.isolation_level = level
    
    # Map common exceptions
    Error = psycopg.Error
    DatabaseError = psycopg.DatabaseError
    IntegrityError = psycopg.IntegrityError
    OperationalError = psycopg.OperationalError
    ProgrammingError = psycopg.ProgrammingError
    
    # Version info
    __version__ = '3.2.10 (psycopg compatibility)'
    
    # Pool compatibility (basic)
    class pool:
        @staticmethod
        def SimpleConnectionPool(*args, **kwargs):
            # Basic pool implementation
            return psycopg.ConnectionPool(*args, **kwargs)
