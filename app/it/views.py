from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.it import it
from app.models import User, UserRole, Branch, AuditLog, EmailConfiguration
from app import db
from datetime import datetime
from sqlalchemy import func
import os
import json

def it_admin_required(f):
    """Decorator to require IT admin access"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.IT_ADMIN:
            flash('Access denied. IT Admin privileges required.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@it.route('/dashboard')
@login_required
@it_admin_required
def dashboard():
    """IT Admin dashboard"""
    # Get system statistics
    total_users = User.query.count()
    total_branches = Branch.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    
    # Get users by role
    users_by_role = db.session.query(
        User.role, func.count(User.id)
    ).group_by(User.role).all()
    
    role_stats = {role.value: count for role, count in users_by_role}
    
    # Recent audit logs
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    
    return render_template('it/dashboard.html',
                          total_users=total_users,
                          total_branches=total_branches,
                          active_users=active_users,
                          role_stats=role_stats,
                          recent_logs=recent_logs)

@it.route('/email_config')
@login_required
@it_admin_required
def email_config():
    """Email configuration page"""
    return render_template('it/email_config.html')

@it.route('/get_email_config')
@login_required
@it_admin_required
def get_email_config():
    """Get current email configuration from database"""
    try:
        # Get active configuration from database
        email_config = EmailConfiguration.get_active_config()
        
        if email_config:
            config = {
                'MAIL_SERVER': email_config.mail_server,
                'MAIL_PORT': str(email_config.mail_port),
                'MAIL_USE_TLS': 'true' if email_config.mail_use_tls else 'false',
                'MAIL_USERNAME': email_config.mail_username,
                'MAIL_PASSWORD': '***',  # Never send actual password
                'MAIL_DEFAULT_SENDER': email_config.mail_default_sender
            }
        else:
            # Return empty config if none exists
            config = {
                'MAIL_SERVER': '',
                'MAIL_PORT': '587',
                'MAIL_USE_TLS': 'true',
                'MAIL_USERNAME': '',
                'MAIL_PASSWORD': '',
                'MAIL_DEFAULT_SENDER': ''
            }
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting configuration: {str(e)}'
        })

@it.route('/update_email_config', methods=['POST'])
@login_required
@it_admin_required
def update_email_config():
    """Update email configuration in database"""
    try:
        data = request.get_json()
        
        # Get current active configuration
        current_config = EmailConfiguration.get_active_config()
        
        # Determine encryption settings
        mail_use_tls = data.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
        mail_use_ssl = not mail_use_tls  # SSL is opposite of TLS for most cases
        
        if current_config:
            # Update existing configuration
            current_config.mail_server = data.get('MAIL_SERVER', '')
            current_config.mail_port = int(data.get('MAIL_PORT', 587))
            current_config.mail_use_tls = mail_use_tls
            current_config.mail_use_ssl = mail_use_ssl
            current_config.mail_username = data.get('MAIL_USERNAME', '')
            current_config.mail_default_sender = data.get('MAIL_DEFAULT_SENDER', '')
            current_config.updated_at = datetime.utcnow()
            
            # Only update password if provided and not the placeholder
            if data.get('MAIL_PASSWORD') and data.get('MAIL_PASSWORD') != '***':
                current_config.mail_password = data.get('MAIL_PASSWORD', '')
        else:
            # Create new configuration
            new_config = EmailConfiguration(
                mail_server=data.get('MAIL_SERVER', ''),
                mail_port=int(data.get('MAIL_PORT', 587)),
                mail_use_tls=mail_use_tls,
                mail_use_ssl=mail_use_ssl,
                mail_username=data.get('MAIL_USERNAME', ''),
                mail_password=data.get('MAIL_PASSWORD', ''),
                mail_default_sender=data.get('MAIL_DEFAULT_SENDER', ''),
                created_by=current_user.id,
                is_active=True
            )
            db.session.add(new_config)
            current_config = new_config
        
        # Save to database
        db.session.commit()
        
        # Update Flask app config with new settings
        from flask import current_app
        from app import mail
        
        current_app.config['MAIL_SERVER'] = current_config.mail_server
        current_app.config['MAIL_PORT'] = current_config.mail_port
        current_app.config['MAIL_USE_TLS'] = current_config.mail_use_tls
        current_app.config['MAIL_USE_SSL'] = current_config.mail_use_ssl
        current_app.config['MAIL_USERNAME'] = current_config.mail_username
        current_app.config['MAIL_PASSWORD'] = current_config.mail_password
        current_app.config['MAIL_DEFAULT_SENDER'] = current_config.mail_default_sender
        
        # Reinitialize mail with new config
        mail.init_app(current_app)
        
        # Trigger graceful restart in production to apply settings across all workers
        if os.environ.get('FLASK_ENV') == 'production':
            try:
                # Create tmp directory if it doesn't exist
                if not os.path.exists('tmp'):
                    os.makedirs('tmp')
                # Touch the restart file to trigger gunicorn reload
                with open('tmp/restart.txt', 'w') as f:
                    f.write(f'Restart triggered at {datetime.utcnow()} UTC\n')
            except Exception as e:
                # Log error but don't fail the request
                current_app.logger.error(f"Could not trigger app restart: {e}")

        # Log the configuration change
        audit_log = AuditLog(
            user_id=current_user.id,
            action='email_config_update',
            description=f'Email configuration updated by IT Admin - Server: {current_config.mail_server}'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email configuration saved successfully to database'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating configuration: {str(e)}'
        })

@it.route('/test_email_config', methods=['POST'])
@login_required
@it_admin_required
def test_email_config():
    """Test email configuration"""
    try:
        from app.notifications import send_test_notification
        
        # Use current user's email for testing
        admin_email = current_user.email
        if not admin_email:
            return jsonify({
                'success': False,
                'message': 'No email address found for current user'
            })
        
        success, message = send_test_notification(admin_email)
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error testing email: {str(e)}'
        })

@it.route('/test_cashier_notification', methods=['POST'])
@login_required
@it_admin_required
def test_cashier_notification():
    """Test cashier logout notification manually"""
    try:
        from app.notifications import send_cashier_logout_notification
        from app.models import User, UserRole
        
        # Find a cashier to test with
        cashier = User.query.filter(User.role == UserRole.CASHIER).first()
        if not cashier:
            return jsonify({
                'success': False,
                'message': 'No cashier found in system for testing'
            })
        
        # Test the notification
        success = send_cashier_logout_notification(cashier.id)
        
        return jsonify({
            'success': success,
            'message': f'Test notification sent for cashier: {cashier.get_full_name()}' if success else 'Failed to send test notification'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error testing cashier notification: {str(e)}'
        })

@it.route('/users')
@login_required
@it_admin_required
def users():
    """User management page"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get all users with pagination
    users_query = User.query.order_by(User.created_at.desc())
    users_pagination = users_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get all branches for user assignment
    branches = Branch.query.filter_by(is_active=True).all()
    
    return render_template('it/users.html',
                          users=users_pagination.items,
                          pagination=users_pagination,
                          branches=branches)

@it.route('/create_user', methods=['POST'])
@login_required
@it_admin_required
def create_user():
    """Create new user (IT can create any role)"""
    try:
        data = request.get_json()
        
        # Check if username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            })
        
        # Check if email already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({
                'success': False,
                'message': 'Email already exists'
            })
        
        # Create new user
        user = User(
            username=data['username'],
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            role=UserRole(data['role']),
            branch_id=data.get('branch_id') if data.get('branch_id') else None,
            is_active=data.get('is_active', True)
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        # Log the user creation
        audit_log = AuditLog(
            user_id=current_user.id,
            action='user_create',
            description=f'Created user: {user.username} ({user.role.value})'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {user.username} created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error creating user: {str(e)}'
        })

@it.route('/update_user/<int:user_id>', methods=['POST'])
@login_required
@it_admin_required
def update_user(user_id):
    """Update user details"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        # Update user fields
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.role = UserRole(data.get('role', user.role.value))
        user.branch_id = data.get('branch_id') if data.get('branch_id') else None
        user.is_active = data.get('is_active', user.is_active)
        
        # Update password if provided
        if data.get('password'):
            user.set_password(data['password'])
        
        db.session.commit()
        
        # Log the user update
        audit_log = AuditLog(
            user_id=current_user.id,
            action='user_update',
            description=f'Updated user: {user.username} ({user.role.value})'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {user.username} updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating user: {str(e)}'
        })

@it.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@it_admin_required
def delete_user(user_id):
    """Delete user (soft delete by deactivating)"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Don't allow deleting self
        if user.id == current_user.id:
            return jsonify({
                'success': False,
                'message': 'Cannot delete your own account'
            })
        
        # Soft delete by deactivating
        user.is_active = False
        db.session.commit()
        
        # Log the user deletion
        audit_log = AuditLog(
            user_id=current_user.id,
            action='user_delete',
            description=f'Deactivated user: {user.username}'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {user.username} deactivated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deactivating user: {str(e)}'
        })

@it.route('/system_settings')
@login_required
@it_admin_required
def system_settings():
    """System settings page"""
    return render_template('it/system_settings.html')

@it.route('/audit_logs')
@login_required
@it_admin_required
def audit_logs():
    """View all audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs_query = AuditLog.query.order_by(AuditLog.created_at.desc())
    logs_pagination = logs_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('it/audit_logs.html',
                          logs=logs_pagination.items,
                          pagination=logs_pagination)
