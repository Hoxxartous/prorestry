#!/usr/bin/env python3
"""
WSGI entry point for Restaurant POS - Render deployment
Optimized for PostgreSQL + SocketIO + Eventlet
"""

# CRITICAL: Monkey patch eventlet BEFORE any other imports
import eventlet
eventlet.monkey_patch()

import os
import sys
import logging
from config import ProductionConfig

# Set environment to production
os.environ['FLASK_ENV'] = 'production'

# Create the Flask application with production config
from app import create_app, socketio
app = create_app(ProductionConfig)

# Configure logging for Gunicorn/Render
if __name__ != "__main__":
    # When running under Gunicorn, use Gunicorn's logger
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)

# Ensure we're using PostgreSQL (no SQLite fallback in production)
database_url = os.environ.get('DATABASE_URL')
if not database_url or 'postgres' not in database_url:
    app.logger.error("❌ PostgreSQL DATABASE_URL is required for production deployment")
    sys.exit(1)

app.logger.info(f"🐘 PostgreSQL database configured: {database_url[:50]}...")

# PRODUCTION DEBUG: Verify deployment configuration
app.logger.info("🔍 PRODUCTION DEPLOYMENT DEBUG:")
app.logger.info("✅ Using ProductionConfig (PostgreSQL-only)")
app.logger.info("✅ wsgi.py entry point (not run.py)")
app.logger.info("🚫 SQLite: COMPLETELY DISABLED")
app.logger.info("🔌 SocketIO: ENABLED for real-time functionality")
app.logger.info("⚡ Eventlet: ENABLED for async performance")

# The SocketIO app is what Gunicorn will serve
# This is critical for WebSocket functionality
application = socketio

if __name__ == "__main__":
    # Development mode fallback
    print("🚀 Starting Restaurant POS in development mode...")
    print("🌐 Server will be available at: http://127.0.0.1:5000")
    print("📝 For production, use: gunicorn -c gunicorn.conf.py wsgi:application")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)