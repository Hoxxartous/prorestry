import os
import logging
import multiprocessing
from datetime import timedelta
from sqlalchemy import event, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
# SQLite import removed for production PostgreSQL deployment
import re
from urllib.parse import urlparse

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # Session configuration for better reliability
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    SESSION_PERMANENT = False  # Don't make sessions permanent by default
    
    # Flask-Login configuration
    REMEMBER_COOKIE_DURATION = timedelta(days=7)  # Remember me duration
    REMEMBER_COOKIE_SECURE = False  # Set to True in production with HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Database configuration - PostgreSQL only for production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://user:pass@localhost/restaurant_pos'
    
    # High-performance database configuration
    @staticmethod
    def get_database_config():
        """Get optimized PostgreSQL configuration for production"""
        # PostgreSQL optimizations for Render FREE PLAN (limited resources)
        return {
            'poolclass': QueuePool,
            'pool_size': 2,                      # Very small pool for free plan
            'max_overflow': 3,                   # Limited overflow
            'pool_timeout': 60,                  # Longer timeout for free plan
            'pool_recycle': 1800,               # Recycle connections every 30 min
            'pool_pre_ping': True,              # Validate connections (critical for SSL issues)
            'pool_reset_on_return': 'commit',   # Reset connections on return
            
            # PostgreSQL-specific optimizations with SSL stability
            'connect_args': {
                'connect_timeout': 30,
                'application_name': 'restaurant_pos',
                'options': '-c default_transaction_isolation=read_committed -c timezone=UTC',
                'sslmode': 'require',  # Changed from 'prefer' to 'require' for Render
                'sslcert': None,
                'sslkey': None,
                'sslrootcert': None,
                'target_session_attrs': 'read-write',
                'keepalives_idle': '600',  # Keep connection alive
                'keepalives_interval': '30',
                'keepalives_count': '3'
            },
            
            # Engine options for performance
            'echo': False,
            'future': True,
            'execution_options': {
                'isolation_level': 'READ_COMMITTED',
                'autocommit': False
            }
        }
    
    # Dynamic engine options based on database type
    @classmethod
    def get_engine_options(cls):
        return cls.get_database_config()
    
    # Set default engine options (will be overridden by subclasses)
    SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # Method to handle database initialization
    @classmethod
    def init_app(cls, app):
        # Handle Render's DATABASE_URL format for PostgreSQL
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            if database_url.startswith('postgres://'):
                # Replace postgres:// with postgresql:// as SQLAlchemy requires
                database_url = re.sub(r'^postgres://', 'postgresql://', database_url)
                app.config['SQLALCHEMY_DATABASE_URI'] = database_url
            else:
                app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        
        # Set engine options for PostgreSQL
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = cls.get_database_config()
        
        # Configure PostgreSQL optimizations
        cls._configure_postgresql_optimizations(app)
    
    
    @staticmethod
    def _configure_postgresql_optimizations(app):
        """Configure PostgreSQL for maximum performance and concurrency"""
        
        @event.listens_for(Engine, "connect")
        def set_postgresql_params(dbapi_connection, connection_record):
            """Set PostgreSQL parameters for optimal performance"""
            try:
                with dbapi_connection.cursor() as cursor:
                    # Connection-level optimizations
                    cursor.execute("SET statement_timeout = '30s'")
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET idle_in_transaction_session_timeout = '60s'")
                    
                    # Performance optimizations
                    cursor.execute("SET work_mem = '32MB'")
                    cursor.execute("SET maintenance_work_mem = '128MB'")
                    cursor.execute("SET effective_cache_size = '256MB'")
                    
                    # Concurrency optimizations
                    cursor.execute("SET max_connections = 200")
                    cursor.execute("SET shared_buffers = '64MB'")
                    
                    # Query optimization
                    cursor.execute("SET random_page_cost = 1.1")
                    cursor.execute("SET seq_page_cost = 1.0")
                    cursor.execute("SET cpu_tuple_cost = 0.01")
                    
                    # Logging optimizations (reduce I/O)
                    cursor.execute("SET log_statement = 'none'")
                    cursor.execute("SET log_min_duration_statement = 1000")  # Log slow queries only
                    
                    # Commit the settings
                    dbapi_connection.commit()
                    
                app.logger.info("PostgreSQL performance optimizations applied")
            except Exception as e:
                app.logger.warning(f"Could not apply PostgreSQL optimizations: {e}")
        
        @event.listens_for(Engine, "first_connect")
        def receive_first_postgresql_connect(dbapi_connection, connection_record):
            """Initialize PostgreSQL connection pool"""
            app.logger.info("First PostgreSQL connection established with performance optimizations")
    
    # Mail configuration (for notifications)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Security settings (moved to main Config class)
    
    # Application settings
    ITEMS_PER_PAGE = 20
    CURRENCY = 'QAR'
    TIMEZONE = os.environ.get('TIMEZONE') or 'Asia/Qatar'
    
    # Logging configuration
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT') or True  # Enable by default
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'postgresql://user:pass@localhost/restaurant_pos_dev'
    LOG_TO_STDOUT = True
    LOG_LEVEL = 'DEBUG'
    
    # Development-specific database optimizations
    @classmethod
    def get_database_config(cls):
        """Get development-optimized database configuration"""
        base_config = super().get_database_config()
        
        # Override for development
        return {
            **base_config,
            'echo': True,  # Enable SQL logging in development
            'pool_size': 5,  # Smaller pool for development
            'max_overflow': 10,
        }

class ProductionConfig(Config):
    DEBUG = False
    
    # Production database configuration - prioritize PostgreSQL for Render
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://user:pass@localhost/restaurant_pos'
    
    # Production-specific optimizations for Render FREE PLAN
    @classmethod
    def get_database_config(cls):
        """Get production-optimized database configuration for Render free plan"""
        # Optimized for Render FREE PLAN - very limited resources
        return {
            'poolclass': QueuePool,
            'pool_size': 2,                      # Very small pool for free plan
            'max_overflow': 3,                   # Limited overflow
            'pool_timeout': 60,                  # Longer timeout for free plan
            'pool_recycle': 1800,               # Recycle connections every 30 min
            'pool_pre_ping': True,              # Validate connections (critical for SSL issues)
            'pool_reset_on_return': 'commit',   # Reset connections on return
            
            # PostgreSQL-specific optimizations with SSL stability
            'connect_args': {
                'connect_timeout': 30,
                'application_name': 'restaurant_pos_prod',
                'options': '-c default_transaction_isolation=read_committed -c timezone=UTC -c statement_timeout=60s',
                'sslmode': 'require',  # Changed from 'prefer' to 'require' for Render
                'sslcert': None,
                'sslkey': None,
                'sslrootcert': None,
                'target_session_attrs': 'read-write',
                'keepalives_idle': '600',  # Keep connection alive
                'keepalives_interval': '30',
                'keepalives_count': '3'
            },
            
            # Engine options for performance
            'echo': False,  # Disable SQL logging in production
            'future': True,
            'execution_options': {
                'isolation_level': 'READ_COMMITTED',
                'autocommit': False,
                'compiled_cache': {}  # Enable query compilation cache
            }
        }
    
    # Additional production settings
    WTF_CSRF_TIME_LIMIT = None  # No CSRF timeout for long sessions
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # 8-hour sessions
    
    # Performance monitoring
    SQLALCHEMY_RECORD_QUERIES = True
    SLOW_DB_QUERY_TIME = 0.5  # Log queries slower than 500ms
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        
        # Production-specific logging
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not app.debug:
            # Set up file logging for production
            if not os.path.exists('logs'):
                os.mkdir('logs')
            
            file_handler = RotatingFileHandler('logs/restaurant_pos.log',
                                             maxBytes=10240000, backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            
            app.logger.setLevel(logging.INFO)
            app.logger.info('Restaurant POS startup - Production Mode')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or 'postgresql://user:pass@localhost/restaurant_pos_test'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}