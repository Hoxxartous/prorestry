import os
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config


class EdgeConfig(Config):
    """
    Branch Edge configuration using local SQLite for offline operation.
    This avoids PostgreSQL-specific optimizations and tunes SQLite for concurrency.
    """
    DEBUG = False
    EDGE_MODE = True

    # Local SQLite database path (override with EDGE_DATABASE_URL if needed)
    SQLALCHEMY_DATABASE_URI = os.environ.get('EDGE_DATABASE_URL') or 'sqlite:///edge.sqlite3'

    @classmethod
    def get_database_config(cls):
        """SQLite-friendly engine options."""
        return {
            'pool_pre_ping': True,
            'echo': False,
            'future': True,
            'connect_args': {
                # Required for multithreaded Flask-SocketIO environment with SQLite
                'check_same_thread': False,
                # SQLite-specific timeout (seconds)
                'timeout': 30.0,
            }
        }

    @classmethod
    def init_app(cls, app):
        # Apply SQLite engine options and mark EDGE mode
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = cls.get_database_config()
        app.config['EDGE_MODE'] = True

        # Install SQLite PRAGMA optimizations on connect
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, connection_record):
            try:
                module_name = getattr(dbapi_connection, "__class__", type(dbapi_connection)).__module__
                if 'sqlite3' in module_name.lower():
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.execute("PRAGMA busy_timeout=5000")
                    cursor.close()
            except Exception:
                # Avoid failing app startup due to pragma issues
                pass
