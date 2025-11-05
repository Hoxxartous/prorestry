"""
Security Headers Module for Restaurant POS System
Addresses multiple security vulnerabilities found in security scan:
- HSTS (HTTP Strict Transport Security)
- X-Frame-Options (Clickjacking protection)
- Content Security Policy (CSP)
- X-Content-Type-Options (MIME sniffing protection)
- CSRF Protection
- Session Security
"""

from flask import Flask, request, session, g
from functools import wraps
import secrets
import hashlib
import time
from datetime import datetime, timedelta


class SecurityHeaders:
    """Security headers manager for Flask application"""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize security headers with Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        
        # Configure secure session settings
        app.config.update({
            'SESSION_COOKIE_SECURE': True,  # Only send over HTTPS
            'SESSION_COOKIE_HTTPONLY': True,  # Prevent XSS access to cookies
            'SESSION_COOKIE_SAMESITE': 'Lax',  # CSRF protection
            'PERMANENT_SESSION_LIFETIME': timedelta(hours=8),  # Session timeout
        })
    
    def before_request(self):
        """Process requests before handling"""
        # Generate CSRF token for each request
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        
        # Store CSRF token in g for template access
        g.csrf_token = session['csrf_token']
        
        # Regenerate session ID periodically for security
        if 'session_created' not in session:
            session['session_created'] = time.time()
        elif time.time() - session['session_created'] > 3600:  # 1 hour
            self._regenerate_session_id()
    
    def after_request(self, response):
        """Add security headers to all responses"""
        
        # HTTP Strict Transport Security (HSTS)
        # Forces HTTPS connections for 1 year, includes subdomains
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # X-Frame-Options - Prevent clickjacking attacks
        response.headers['X-Frame-Options'] = 'DENY'
        
        # X-Content-Type-Options - Prevent MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # X-XSS-Protection - Enable XSS filtering
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy - Control referrer information
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy (CSP)
        csp_policy = self._build_csp_policy()
        response.headers['Content-Security-Policy'] = csp_policy
        
        # Remove server information
        response.headers.pop('Server', None)
        
        # Cache control for sensitive pages
        if request.endpoint and any(sensitive in request.endpoint for sensitive in ['auth', 'admin', 'pos']):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        return response
    
    def _build_csp_policy(self):
        """Build Content Security Policy based on application needs"""
        # Allow specific trusted CDNs for Bootstrap, jQuery, etc.
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://code.jquery.com https://cdn.socket.io",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: https:",
            "connect-src 'self' wss: ws:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'"
        ]
        return "; ".join(csp_directives)
    
    def _regenerate_session_id(self):
        """Regenerate session ID for security"""
        # Store current session data
        session_data = dict(session)
        
        # Clear session
        session.clear()
        
        # Restore data with new session ID
        session.update(session_data)
        session['session_created'] = time.time()
        session['csrf_token'] = secrets.token_hex(32)


class CSRFProtection:
    """CSRF Protection implementation"""
    
    @staticmethod
    def generate_csrf_token():
        """Generate a new CSRF token"""
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return session['csrf_token']
    
    @staticmethod
    def validate_csrf_token(token):
        """Validate CSRF token"""
        return token and session.get('csrf_token') == token
    
    @staticmethod
    def csrf_protect(f):
        """Decorator to protect routes from CSRF attacks"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method == 'POST':
                token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
                if not CSRFProtection.validate_csrf_token(token):
                    from flask import abort
                    abort(403, description="CSRF token missing or invalid")
            return f(*args, **kwargs)
        return decorated_function


class SessionSecurity:
    """Enhanced session security management"""
    
    @staticmethod
    def init_session_security(app):
        """Initialize session security settings"""
        
        @app.before_request
        def check_session_security():
            """Check session security on each request"""
            
            # Skip security checks for static files
            if request.endpoint == 'static':
                return
            
            # Check for session hijacking attempts
            if 'user_agent_hash' in session:
                current_ua_hash = hashlib.sha256(
                    request.headers.get('User-Agent', '').encode()
                ).hexdigest()
                
                if session['user_agent_hash'] != current_ua_hash:
                    session.clear()
                    from flask import flash, redirect, url_for
                    flash('Session security violation detected. Please log in again.', 'error')
                    return redirect(url_for('auth.login'))
            else:
                # Store user agent hash for session validation
                session['user_agent_hash'] = hashlib.sha256(
                    request.headers.get('User-Agent', '').encode()
                ).hexdigest()
            
            # Check session timeout
            if 'last_activity' in session:
                if datetime.now() - datetime.fromisoformat(session['last_activity']) > timedelta(hours=8):
                    session.clear()
                    from flask import flash, redirect, url_for
                    flash('Session expired. Please log in again.', 'info')
                    return redirect(url_for('auth.login'))
            
            # Update last activity
            session['last_activity'] = datetime.now().isoformat()


def init_security(app):
    """Initialize all security features"""
    
    # Initialize security headers
    security_headers = SecurityHeaders(app)
    
    # Initialize session security
    SessionSecurity.init_session_security(app)
    
    # Add CSRF token to template context
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=CSRFProtection.generate_csrf_token())
    
    # Template function for CSRF token
    @app.template_global()
    def csrf_token():
        return CSRFProtection.generate_csrf_token()
    
    app.logger.info("Security features initialized successfully")
    
    return app


# Utility functions for templates
def get_csrf_token():
    """Get CSRF token for use in templates"""
    return CSRFProtection.generate_csrf_token()


# Security middleware for Socket.IO sessions
class SocketIOSecurity:
    """Security enhancements for Socket.IO connections"""
    
    @staticmethod
    def validate_socketio_session(auth_data):
        """Validate Socket.IO session data"""
        # Implement session validation for Socket.IO
        # This helps with the "Session ID in URL Rewrite" vulnerability
        return True  # Implement actual validation logic
    
    @staticmethod
    def secure_socketio_config():
        """Return secure Socket.IO configuration"""
        return {
            'cors_allowed_origins': [],  # Restrict to specific origins in production
            'cookie': False,  # Disable cookies for Socket.IO to prevent URL session exposure
            'transports': ['websocket'],  # Prefer websocket over polling to avoid URL sessions
        }
