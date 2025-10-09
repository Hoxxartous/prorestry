from app import create_app
from config import DevelopmentConfig, ProductionConfig
import os

def main():
    """Create and return the Flask app with automatic initialization"""
    # Choose config based on environment or DATABASE_URL
    if os.environ.get('DATABASE_URL'):
        # If DATABASE_URL is set, use ProductionConfig (PostgreSQL)
        config_class = ProductionConfig
        print("🐘 Using PostgreSQL configuration")
    else:
        # Fallback to DevelopmentConfig (SQLite) for local development only
        config_class = DevelopmentConfig
        print("💾 Using SQLite for local development")
    
    app = create_app(config_class)
    return app

if __name__ == '__main__':
    app = main()
    # Import socketio from app
    from app import socketio
    # Run with debug=False in production
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    socketio.run(app, debug=debug_mode, host='127.0.0.1', port=5000)