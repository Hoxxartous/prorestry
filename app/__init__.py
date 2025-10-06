from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from config import Config
import os
import logging
from logging.handlers import RotatingFileHandler
import sys

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    socketio.init_app(app, cors_allowed_origins="*")
    
    # Register blueprints
    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    
    from app.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    
    from app.pos import pos as pos_blueprint
    app.register_blueprint(pos_blueprint, url_prefix='/pos')
    
    # Register Super User blueprint for multi-branch management
    from app.superuser import superuser as superuser_blueprint
    app.register_blueprint(superuser_blueprint, url_prefix='/superuser')
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    
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
    
    # Initialize database automatically on app startup
    def init_db():
        """Initialize database with multi-branch support automatically"""
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
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
                if not Branch.query.first() and not User.query.first():
                    app.logger.info("Tables exist but no data found, initializing data...")
                    print("INITIALIZING DATA FOR EXISTING TABLES...")
                    from app.db_init import init_multibranch_db
                    init_multibranch_db(app)
                    print("DATA INITIALIZATION COMPLETED!")
                else:
                    app.logger.info("Database already initialized with data")
                
        except Exception as e:
            app.logger.error(f"Database initialization error: {str(e)}")
            print(f"Database initialization failed: {str(e)}")
            print("Please check your database configuration and try again.")
    
    # Configure logging
    configure_logging(app)
    
    # Call init_db when app starts
    with app.app_context():
        try:
            init_db()
        except Exception as e:
            app.logger.error(f"Startup database initialization failed: {str(e)}")
            print(f"Startup initialization failed: {str(e)}")
    
    return app

def configure_logging(app):
    """Configure application logging"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Set log level based on configuration
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    
    # Configure file handler for all logs
    file_handler = RotatingFileHandler('logs/restaurant_pos.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(log_level)
    app.logger.addHandler(file_handler)
    
    # Configure console handler if LOG_TO_STDOUT is enabled
    if app.config.get('LOG_TO_STDOUT'):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        stream_handler.setLevel(log_level)
        app.logger.addHandler(stream_handler)
    
    # Set the application logger level
    app.logger.setLevel(log_level)
    
    # Log application startup
    app.logger.info('Restaurant POS application startup')
    app.logger.info(f'Log level set to: {app.config.get("LOG_LEVEL", "INFO")}')
    app.logger.info(f'Debug mode: {app.config.get("DEBUG", False)}')
