# Ensure eventlet monkey patching happens first (for production)
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import re
from sqlalchemy import event
from sqlalchemy.engine import Engine

# PostgreSQL driver compatibility - prefer psycopg2-binary if available
try:
    import psycopg2
except ImportError:
    # Fallback to psycopg if psycopg2 not available
    pass

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_mail import Mail
from config import Config

# Disable Postgres tuning hooks on platforms like Render unless explicitly allowed
try:
    if os.getenv('ALLOW_PG_TUNING', '0') not in ('1', 'true', 'True'):
        # Monkey-patch the tuning function to a no-op to avoid unsafe SETs
        Config._configure_postgresql_optimizations = staticmethod(lambda app: None)
except Exception:
    # Non-fatal if monkey patching fails
    pass

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO()
mail = Mail()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Apply configuration-specific initialization (engine options, DB tuning)
    if hasattr(config_class, 'init_app'):
        try:
            config_class.init_app(app)
        except Exception as e:
            # Do not block startup if env-specific init raises
            app.logger.warning(f"Config.init_app encountered an issue: {e}")
    
    # Sanitize invalid Postgres options injected via config.py for Render
    try:
        engine_options = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
        connect_args = engine_options.get('connect_args', {}) or {}
        opts = connect_args.get('options')
        if isinstance(opts, str) and 'default_transaction_isolation=read_committed' in opts:
            # Remove the invalid GUC; keep everything else (timezone, statement_timeout)
            sanitized = opts.replace('-c default_transaction_isolation=read_committed', '')
            # Clean up extra whitespace
            sanitized = ' '.join(sanitized.split())
            connect_args['options'] = sanitized
            engine_options['connect_args'] = connect_args
            app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
            app.logger.info('Sanitized Postgres options: removed default_transaction_isolation=read_committed')
    except Exception as se:
        app.logger.warning(f'Could not sanitize Postgres options: {se}')

    # Prevent transaction aborts caused by unsafe session-level SETs in global connect hooks
    # Ensure autocommit for the duration of any connect-time tuning, then restore it.
    @event.listens_for(Engine, "connect", insert=True)
    def _pre_connect_set_autocommit(dbapi_connection, connection_record):
        try:
            module_name = getattr(dbapi_connection, "__class__", type(dbapi_connection)).__module__
            if 'psycopg' in module_name or 'psycopg2' in module_name:
                if hasattr(dbapi_connection, 'autocommit'):
                    dbapi_connection.autocommit = True
        except Exception:
            # Best effort: ignore if not supported
            pass

    @event.listens_for(Engine, "connect")
    def _post_connect_restore_autocommit(dbapi_connection, connection_record):
        try:
            module_name = getattr(dbapi_connection, "__class__", type(dbapi_connection)).__module__
            if 'psycopg' in module_name or 'psycopg2' in module_name:
                if hasattr(dbapi_connection, 'autocommit'):
                    # Rollback any aborted state just in case
                    try:
                        dbapi_connection.rollback()
                    except Exception:
                        pass
                    dbapi_connection.autocommit = False
        except Exception:
            pass

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Your session has expired. Please log in again.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'  # Strong session protection
    socketio.init_app(app, cors_allowed_origins="*")
    mail.init_app(app)
    
    # Initialize session manager for better session handling
    from app.session_manager import init_session_manager
    init_session_manager(app)
    
    # Handle 401 Unauthorized errors globally
    @app.errorhandler(401)
    def handle_unauthorized(error):
        """Handle 401 Unauthorized errors with session cleanup"""
        from flask import session, redirect, url_for, flash, request
        
        # Clear stale session data
        session.clear()
        
        # Log the unauthorized access
        app.logger.info(f"401 Unauthorized error handled for {request.url}")
        
        # Redirect to login with helpful message
        flash('Your session has expired. Please log in again.', 'info')
        return redirect(url_for('auth.login'))
    
    # Register blueprints
    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    
    from app.pos import pos as pos_blueprint
    app.register_blueprint(pos_blueprint, url_prefix='/pos')
    
    from app.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    
    from app.superuser import superuser as superuser_blueprint
    app.register_blueprint(superuser_blueprint, url_prefix='/superuser')
    
    from app.cashier import cashier as cashier_blueprint
    app.register_blueprint(cashier_blueprint, url_prefix='/cashier')
    
    from app.kitchen import kitchen as kitchen_blueprint
    app.register_blueprint(kitchen_blueprint, url_prefix='/kitchen')
    
    from app.it import it as it_blueprint
    app.register_blueprint(it_blueprint, url_prefix='/it')
    
    # Register debug blueprint (for troubleshooting)
    from app.debug_routes import debug_bp
    app.register_blueprint(debug_bp)
    
    # Register cloud sync API (safe to register everywhere; requires token on cloud)
    try:
        from app.sync_api import sync_api
        app.register_blueprint(sync_api)
    except Exception as e:
        app.logger.warning(f"Sync API not registered: {e}")
    
    # User loader for Flask-Login with comprehensive error handling
    @login_manager.user_loader
    def load_user(user_id):
        """Load user with robust error handling and session cleanup"""
        if not user_id:
            return None
            
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            app.logger.warning(f"Invalid user_id format in session: {user_id}")
            return None
        
        # Use SSL-aware database connection handling
        try:
            from app.db_connection_handler import safe_db_operation
            
            def _load_user():
                # Import User model within the function to avoid circular imports
                from app.models import User
                from sqlalchemy import text
                
                # Check if database is accessible
                db.session.execute(text("SELECT 1")).scalar()
                
                # Load user from database
                user = User.query.get(user_id)
                if user and user.is_active:
                    return user
                elif user and not user.is_active:
                    app.logger.warning(f"Inactive user attempted to load session: {user.username}")
                    return None
                else:
                    app.logger.warning(f"User not found in database: {user_id}")
                    return None
            
            return safe_db_operation(_load_user)
            
        except Exception as e:
            app.logger.error(f"User loader failed with SSL-aware handling: {e}")
            return None
        return None
    
    # Handle unauthorized access gracefully
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized access with proper session cleanup"""
        from flask import request, session, redirect, url_for, flash
        
        # Clear any stale session data
        session.clear()
        
        # Log the unauthorized access attempt
        app.logger.info(f"Unauthorized access attempt from {request.remote_addr} to {request.url}")
        
        # Redirect to login with helpful message
        flash('Your session has expired. Please log in again.', 'info')
        return redirect(url_for('auth.login'))
    
    # Context processors for templates
    @app.context_processor
    def inject_user_branch_info():
        from flask_login import current_user
        if current_user.is_authenticated:
            return {
                'current_branch': current_user.branch,
                'accessible_branches': current_user.get_accessible_branches(),
                'is_super_user': current_user.is_super_user(),
                'is_branch_admin': current_user.is_branch_admin()
            }
        return {}
    
    # Template filters for timezone handling
    @app.template_filter('local_datetime')
    def local_datetime_filter(utc_datetime, format_str='%Y-%m-%d %H:%M:%S'):
        """Convert UTC datetime to local timezone and format it"""
        if not utc_datetime:
            return ''
        try:
            from app.models import TimezoneManager
            return TimezoneManager.format_local_time(utc_datetime, format_str)
        except Exception as e:
            app.logger.error(f"Error formatting datetime: {e}")
            return utc_datetime.strftime(format_str) if utc_datetime else ''
    
    @app.template_filter('local_date')
    def local_date_filter(utc_datetime):
        """Convert UTC datetime to local date"""
        if not utc_datetime:
            return ''
        try:
            from app.models import TimezoneManager
            return TimezoneManager.format_local_time(utc_datetime, '%Y-%m-%d')
        except Exception as e:
            app.logger.error(f"Error formatting date: {e}")
            return utc_datetime.strftime('%Y-%m-%d') if utc_datetime else ''
    
    @app.template_filter('local_time')
    def local_time_filter(utc_datetime):
        """Convert UTC datetime to local time"""
        if not utc_datetime:
            return ''
        try:
            from app.models import TimezoneManager
            return TimezoneManager.format_local_time(utc_datetime, '%H:%M:%S')
        except Exception as e:
            app.logger.error(f"Error formatting time: {e}")
            return utc_datetime.strftime('%H:%M:%S') if utc_datetime else ''
    
    # Additional specific format filters
    @app.template_filter('local_datetime_short')
    def local_datetime_short_filter(utc_datetime):
        """Convert UTC datetime to local timezone with short format"""
        if not utc_datetime:
            return ''
        try:
            from app.models import TimezoneManager
            return TimezoneManager.format_local_time(utc_datetime, '%Y-%m-%d %H:%M')
        except Exception as e:
            app.logger.error(f"Error formatting datetime: {e}")
            return utc_datetime.strftime('%Y-%m-%d %H:%M') if utc_datetime else ''
    
    @app.template_filter('local_time_short')
    def local_time_short_filter(utc_datetime):
        """Convert UTC datetime to local time with short format"""
        if not utc_datetime:
            return ''
        try:
            from app.models import TimezoneManager
            return TimezoneManager.format_local_time(utc_datetime, '%H:%M')
        except Exception as e:
            app.logger.error(f"Error formatting time: {e}")
            return utc_datetime.strftime('%H:%M') if utc_datetime else ''
    
    # Initialize database automatically on app startup
    def init_db():
        """Initialize database with multi-branch support automatically"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                app.logger.info(f"Database initialization attempt {attempt + 1}/{max_retries}")
                
                # Test basic database connection first
                from sqlalchemy import text
                db.session.execute(text("SELECT 1")).scalar()
                app.logger.info("Database connection successful")
                
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                existing_tables = inspector.get_table_names()
                app.logger.info(f"Found {len(existing_tables)} existing tables: {existing_tables}")
                
                # Check if database is completely empty or missing key tables
                if not existing_tables or 'users' not in existing_tables or 'branches' not in existing_tables:
                    app.logger.info("Database not initialized or incomplete, starting automatic initialization...")
                    print("=" * 60)
                    print("FIRST TIME SETUP - INITIALIZING DATABASE...")
                    print("=" * 60)
                    
                    from app.db_init import init_multibranch_db
                    init_multibranch_db(app)
                    
                    print("=" * 60)
                    print("DATABASE INITIALIZATION COMPLETED!")
                    print("Default Login Credentials:")
                    print("   Super Admin: superadmin / SuperAdmin123!")
                    print("   Branch Admin: admin1 / admin123")
                    print("   Cashier: cashier1_1 / cashier123")
                    print("=" * 60)
                    
                else:
                    # Double-check that we have actual data, not just empty tables
                    from app.models import Branch, User
                    branch_count = Branch.query.count()
                    user_count = User.query.count()
                    app.logger.info(f"Found {branch_count} branches and {user_count} users")
                    
                    if branch_count == 0 or user_count == 0:
                        app.logger.info(f"Incomplete data found (branches: {branch_count}, users: {user_count}), initializing missing data...")
                        print("INITIALIZING MISSING DATA...")
                        from app.db_init import init_multibranch_db
                        init_multibranch_db(app)
                        print("DATA INITIALIZATION COMPLETED!")
                    else:
                        app.logger.info(f"Database already initialized with data (branches: {branch_count}, users: {user_count})")
                
                # If we get here, initialization was successful
                break
                
            except Exception as e:
                app.logger.error(f"Database initialization attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    app.logger.info(f"Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                else:
                    app.logger.error("All database initialization attempts failed")
                    print(f"Database initialization failed after {max_retries} attempts: {str(e)}")
                    print("Please check your database configuration and try again.")
    
    # Configure logging
    configure_logging(app)
    
    # Call init_db when app starts
    with app.app_context():
        try:
            init_db()
            # Ensure sync columns exist for all syncable tables (Orders, Customers, etc.)
            from sqlalchemy import text
            
            # Tables that need sync columns (external_id, synced_at, updated_at)
            sync_tables = [
                ('orders', True, True, True),           # (table, needs_external_id, needs_synced_at, needs_updated_at)
                ('customers', True, True, True),
                ('order_items', True, False, False),
                ('payments', True, False, False),
                ('branches', True, False, False),
                ('users', True, False, True),
                ('categories', True, False, True),
                ('menu_items', True, False, False),
                ('tables', True, False, True),
                ('cashier_sessions', True, True, True),
                ('kitchen_orders', True, True, True),
            ]
            
            for table_name, needs_ext_id, needs_synced, needs_updated in sync_tables:
                try:
                    if needs_ext_id:
                        try:
                            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS external_id VARCHAR(64)"))
                        except Exception:
                            try:
                                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN external_id VARCHAR(64)"))
                            except Exception:
                                pass
                    
                    if needs_synced:
                        try:
                            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP"))
                        except Exception:
                            try:
                                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN synced_at TIMESTAMP"))
                            except Exception:
                                pass
                    
                    if needs_updated:
                        try:
                            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
                        except Exception:
                            try:
                                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN updated_at TIMESTAMP"))
                            except Exception:
                                pass
                    
                    db.session.commit()
                except Exception as e_table:
                    db.session.rollback()
                    app.logger.debug(f"Sync column migration for {table_name}: {e_table}")
            
            app.logger.info("Sync column migrations completed")
            
            # Load email configuration from database
            load_email_config_from_db(app)
            # Start Edge sync worker if running in Edge mode
            try:
                if app.config.get('EDGE_MODE'):
                    from app.edge_sync import start_edge_sync_worker
                    start_edge_sync_worker(app)
            except Exception as e_sync:
                app.logger.warning(f"Edge sync worker not started: {e_sync}")
        except Exception as e:
            app.logger.error(f"Startup database initialization failed: {str(e)}")
            print(f"Startup initialization failed: {str(e)}")
    
    return app

def load_email_config_from_db(app):
    """Load email configuration from database and update Flask config"""
    try:
        from app.models import EmailConfiguration
        
        # Get active email configuration
        email_config = EmailConfiguration.get_active_config()
        
        if email_config:
            # Update Flask app config with database values
            app.config['MAIL_SERVER'] = email_config.mail_server
            app.config['MAIL_PORT'] = email_config.mail_port
            app.config['MAIL_USE_TLS'] = email_config.mail_use_tls
            app.config['MAIL_USE_SSL'] = email_config.mail_use_ssl
            app.config['MAIL_USERNAME'] = email_config.mail_username
            app.config['MAIL_PASSWORD'] = email_config.mail_password
            app.config['MAIL_DEFAULT_SENDER'] = email_config.mail_default_sender
            
            # Reinitialize mail with new config
            mail.init_app(app)
            
            app.logger.info(f"✅ Email configuration loaded from database: {email_config.mail_server}:{email_config.mail_port}")
            print(f"✅ Email configuration loaded: {email_config.mail_server}:{email_config.mail_port}")
        else:
            app.logger.info("ℹ️ No email configuration found in database - using environment variables")
            print("ℹ️ No email configuration found in database - using environment variables")
            
    except Exception as e:
        app.logger.error(f"❌ Failed to load email configuration from database: {str(e)}")
        print(f"❌ Failed to load email configuration from database: {str(e)}")

def configure_logging(app):
    """Configure application logging"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Set log level based on configuration
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    
    # Configure file handler for all logs with UTF-8 encoding
    file_handler = RotatingFileHandler('logs/restaurant_pos.log', maxBytes=10240000, backupCount=10, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(log_level)
    app.logger.addHandler(file_handler)
    
    # Configure console handler if LOG_TO_STDOUT is enabled with UTF-8 encoding
    if app.config.get('LOG_TO_STDOUT'):
        import sys
        # Use UTF-8 encoding for console output on Windows
        if sys.platform.startswith('win'):
            import io
            # Wrap stdout with UTF-8 encoding
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        stream_handler.setLevel(log_level)
        app.logger.addHandler(stream_handler)
    
    # Set the application logger level
    app.logger.setLevel(log_level)
    
    # Register template filters for modifier pricing
    from app.template_filters import register_template_filters
    register_template_filters(app)
    
    # Log application startup
    app.logger.info('Restaurant POS application startup')
    app.logger.info(f'Log level set to: {app.config.get("LOG_LEVEL", "INFO")}')
    app.logger.info(f'Debug mode: {app.config.get("DEBUG", False)}')
    
    return app
