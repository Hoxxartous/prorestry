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
    
    # DB API 2.0 required attributes
    paramstyle = 'pyformat'
    threadsafety = 2
    apilevel = '2.0'
    
    # Create compatibility classes and functions
    class extras:
        @staticmethod
        def RealDictCursor():
            return dict_row
        
        @staticmethod
        def DictCursor():
            return dict_row
        
        @staticmethod
        def register_uuid(oids=None, conn_or_curs=None):
            # UUID registration compatibility - psycopg v3 handles this automatically
            pass
        
        @staticmethod
        def register_default_json(conn_or_curs=None, globally=False, loads=None):
            # JSON registration compatibility - psycopg v3 handles this automatically
            pass
        
        @staticmethod
        def register_default_jsonb(conn_or_curs=None, globally=False, loads=None):
            # JSONB registration compatibility - psycopg v3 handles this automatically
            pass
    
    class extensions:
        # Use string constants instead of enum values
        ISOLATION_LEVEL_AUTOCOMMIT = 'autocommit'
        ISOLATION_LEVEL_READ_COMMITTED = 'read_committed'
        ISOLATION_LEVEL_SERIALIZABLE = 'serializable'
        
        @staticmethod
        def set_isolation_level(conn, level):
            # Map string levels to psycopg IsolationLevel enum
            level_map = {
                'autocommit': psycopg.IsolationLevel.AUTOCOMMIT,
                'read_committed': psycopg.IsolationLevel.READ_COMMITTED,
                'serializable': psycopg.IsolationLevel.SERIALIZABLE
            }
            if level in level_map:
                conn.isolation_level = level_map[level]
            else:
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
            # Return a simple connection function for basic compatibility
            def get_connection():
                return psycopg.connect(*args, **kwargs)
            return get_connection
