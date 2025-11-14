from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth
from app.models import User, AuditLog, UserRole
from app import db
from datetime import datetime
import pytz

@auth.route('/login', methods=['GET', 'POST'])
def login():
    # Clear any stale session data on login page access
    if not current_user.is_authenticated and request.method == 'GET':
        from flask import session
        session.clear()
    
    if current_user.is_authenticated:
        current_app.logger.info(f"Already authenticated user {current_user.username} attempted to access login page")
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember_me = bool(request.form.get('remember_me'))
        
        current_app.logger.info(f"Login attempt for username: {username}")
        
        try:
            from app.db_connection_handler import safe_db_operation, DatabaseConnectionManager
            
            def _perform_login():
                # Ensure database is initialized before querying
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                existing_tables = inspector.get_table_names()
                
                if 'users' not in existing_tables:
                    # Database not initialized, initialize it now
                    current_app.logger.info("Database not initialized, initializing now...")
                    from app.db_init import init_db_lazy
                    init_db_lazy(current_app)
                
                user = User.query.filter_by(username=username).first()
                
                # Debug logging
                if user:
                    current_app.logger.info(f"User found: {user.username}, Active: {user.is_active}, Role: {user.role.value}")
                    password_valid = user.check_password(password)
                    current_app.logger.info(f"Password validation result: {password_valid}")
                else:
                    current_app.logger.warning(f"User not found: {username}")
                    # Check if any users exist at all
                    user_count = User.query.count()
                    current_app.logger.info(f"Total users in database: {user_count}")
                
                if user and user.check_password(password) and user.is_active:
                    # Clear any existing session data before login
                    from flask import session
                    session.clear()
                    
                    # Login user with proper session management
                    login_user(user, remember=remember_me)
                    
                    # Update last login time with SSL-aware commit
                    user.last_login = datetime.utcnow()
                    
                    def _commit_login():
                        db.session.commit()
                    
                    safe_db_operation(_commit_login)
                    
                    # Log the login action
                    log_audit_action(user.id, 'login', 'User logged in successfully')
                    current_app.logger.info(f"Successful login for user: {username} (Role: {user.role.value})")
                    
                    # Redirect to appropriate dashboard based on role
                    if user.role == UserRole.SUPER_USER:
                        return redirect(url_for('superuser.dashboard'))
                    elif user.role == UserRole.BRANCH_ADMIN:
                        return redirect(url_for('admin.dashboard'))
                    elif user.role == UserRole.WAITER:
                        return redirect(url_for('pos.table_management'))
                    elif user.role == UserRole.KITCHEN:
                        return redirect(url_for('kitchen.dashboard'))
                    else:
                        return redirect(url_for('pos.index'))
                else:
                    current_app.logger.warning(f"Failed login attempt for username: {username}")
                    flash('Invalid username or password', 'error')
                    return None
            
            # Execute login with SSL error handling
            result = safe_db_operation(_perform_login)
            if result:
                return result
                
        except Exception as e:
            current_app.logger.error(f"Login error: {str(e)}")
            flash('System error occurred. Please try again.', 'error')
    
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    username = current_user.username
    user_id = current_user.id
    user_role = current_user.role
    
    # Log the logout action
    log_audit_action(current_user.id, 'logout', 'User logged out')
    current_app.logger.info(f"User logged out: {username}")
    
    # Send notification to admins if this is a cashier logout
    current_app.logger.info(f"=== LOGOUT DETECTED === User: {username}, Role: {user_role.name}, ID: {user_id}")
    
    if user_role.name == 'CASHIER':
        current_app.logger.info(f"🔔 CASHIER LOGOUT DETECTED - STARTING NOTIFICATION PROCESS")
        current_app.logger.info(f"   Cashier: {username} (ID: {user_id})")
        current_app.logger.info(f"   Timestamp: {datetime.utcnow()}")
        try:
            from app.notifications import send_cashier_logout_notification
            # Send notification asynchronously to avoid blocking logout
            from threading import Thread
            
            # Capture the Flask app instance before starting the thread
            app = current_app._get_current_object()
            
            # Create a wrapper function that includes the application context
            def notification_with_context():
                with app.app_context():
                    send_cashier_logout_notification(user_id)
            
            notification_thread = Thread(target=notification_with_context)
            notification_thread.daemon = True
            notification_thread.start()
            current_app.logger.info(f"✅ Cashier logout notification thread STARTED for: {username}")
        except Exception as e:
            current_app.logger.error(f"❌ FAILED to initiate logout notification: {str(e)}")
    else:
        current_app.logger.info(f"ℹ️ Non-cashier logout - no notification needed for role: {user_role.name}")
    
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

def log_audit_action(user_id, action, description):
    """Helper function to log audit actions with SSL error handling"""
    try:
        from app.db_connection_handler import safe_db_operation
        
        def _create_audit_log():
            # Get client IP
            if request.headers.get('X-Forwarded-For'):
                ip_address = request.headers.get('X-Forwarded-For').split(',')[0]
            else:
                ip_address = request.environ.get('REMOTE_ADDR')
            
            # Create audit log entry
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                description=description,
                ip_address=ip_address,
                user_agent=request.headers.get('User-Agent')
            )
            
            db.session.add(audit_log)
            db.session.commit()
        
        # Execute with SSL error handling
        safe_db_operation(_create_audit_log)
        
    except Exception as e:
        # Log the error but don't break the main flow
        current_app.logger.error(f"Audit log error: {str(e)}")
        db.session.rollback()