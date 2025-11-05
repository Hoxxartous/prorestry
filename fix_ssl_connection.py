#!/usr/bin/env python3
"""
SSL Connection Fix for PostgreSQL on Render
Diagnoses and fixes SSL connection issues
"""

import os
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_direct_connection():
    """Test direct PostgreSQL connection"""
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found")
            return False
        
        logger.info("🔍 Testing direct PostgreSQL connection...")
        
        # Parse the URL
        parsed = urlparse(database_url)
        
        # Test different SSL modes
        ssl_modes = ['require', 'prefer', 'allow', 'disable']
        
        for ssl_mode in ssl_modes:
            try:
                logger.info(f"Testing SSL mode: {ssl_mode}")
                
                conn = psycopg2.connect(
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    database=parsed.path[1:],  # Remove leading slash
                    user=parsed.username,
                    password=parsed.password,
                    sslmode=ssl_mode,
                    connect_timeout=30,
                    keepalives_idle=600,
                    keepalives_interval=30,
                    keepalives_count=3
                )
                
                cur = conn.cursor()
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                logger.info(f"✅ Connection successful with SSL mode '{ssl_mode}': {version}")
                
                cur.close()
                conn.close()
                return ssl_mode
                
            except Exception as e:
                logger.warning(f"❌ SSL mode '{ssl_mode}' failed: {e}")
                continue
        
        logger.error("All SSL modes failed")
        return False
        
    except Exception as e:
        logger.error(f"Direct connection test failed: {e}")
        return False

def test_sqlalchemy_connection():
    """Test SQLAlchemy connection with different configurations"""
    try:
        from sqlalchemy import create_engine, text
        
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL not found")
            return False
        
        # Fix postgres:// to postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        logger.info("🔍 Testing SQLAlchemy connection...")
        
        # Test configurations
        configs = [
            {
                'name': 'SSL Required with Keepalives',
                'connect_args': {
                    'sslmode': 'require',
                    'connect_timeout': 30,
                    'keepalives_idle': '600',
                    'keepalives_interval': '30',
                    'keepalives_count': '3'
                }
            },
            {
                'name': 'SSL Prefer with Keepalives',
                'connect_args': {
                    'sslmode': 'prefer',
                    'connect_timeout': 30,
                    'keepalives_idle': '600',
                    'keepalives_interval': '30',
                    'keepalives_count': '3'
                }
            },
            {
                'name': 'Basic SSL Required',
                'connect_args': {
                    'sslmode': 'require',
                    'connect_timeout': 30
                }
            }
        ]
        
        for config in configs:
            try:
                logger.info(f"Testing: {config['name']}")
                
                engine = create_engine(
                    database_url,
                    pool_pre_ping=True,
                    pool_recycle=1800,
                    connect_args=config['connect_args']
                )
                
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT version()")).scalar()
                    logger.info(f"✅ {config['name']} successful: {result[:50]}...")
                    
                engine.dispose()
                return config
                
            except Exception as e:
                logger.warning(f"❌ {config['name']} failed: {e}")
                continue
        
        logger.error("All SQLAlchemy configurations failed")
        return False
        
    except Exception as e:
        logger.error(f"SQLAlchemy connection test failed: {e}")
        return False

def test_app_connection():
    """Test connection through the Flask app"""
    try:
        logger.info("🔍 Testing Flask app connection...")
        
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            from sqlalchemy import text
            
            # Test basic connection
            result = db.session.execute(text("SELECT 1")).scalar()
            if result == 1:
                logger.info("✅ Flask app connection successful")
                
                # Test user query (the one that was failing)
                from app.models import User
                user_count = User.query.count()
                logger.info(f"✅ User query successful: {user_count} users found")
                
                return True
            else:
                logger.error("❌ Flask app connection failed")
                return False
                
    except Exception as e:
        logger.error(f"Flask app connection test failed: {e}")
        return False

def apply_ssl_fix():
    """Apply the SSL connection fix"""
    try:
        logger.info("🔧 Applying SSL connection fix...")
        
        # Test which configuration works
        working_ssl_mode = test_direct_connection()
        if not working_ssl_mode:
            logger.error("Could not find working SSL configuration")
            return False
        
        logger.info(f"✅ Found working SSL mode: {working_ssl_mode}")
        
        # Update environment variable for this session
        os.environ['PGSSLMODE'] = working_ssl_mode
        
        # Test the app connection
        if test_app_connection():
            logger.info("🎉 SSL fix applied successfully!")
            return True
        else:
            logger.error("SSL fix did not resolve app connection issues")
            return False
            
    except Exception as e:
        logger.error(f"Failed to apply SSL fix: {e}")
        return False

def main():
    """Main SSL connection diagnostic and fix"""
    logger.info("🚀 Starting SSL Connection Diagnostic and Fix")
    logger.info("=" * 60)
    
    # Step 1: Test direct connection
    logger.info("Step 1: Testing direct PostgreSQL connection...")
    working_ssl_mode = test_direct_connection()
    
    if working_ssl_mode:
        logger.info(f"✅ Direct connection works with SSL mode: {working_ssl_mode}")
    else:
        logger.error("❌ Direct connection failed with all SSL modes")
        return False
    
    # Step 2: Test SQLAlchemy connection
    logger.info("\nStep 2: Testing SQLAlchemy connection...")
    working_config = test_sqlalchemy_connection()
    
    if working_config:
        logger.info(f"✅ SQLAlchemy connection works with: {working_config['name']}")
    else:
        logger.error("❌ SQLAlchemy connection failed with all configurations")
        return False
    
    # Step 3: Test Flask app connection
    logger.info("\nStep 3: Testing Flask app connection...")
    app_works = test_app_connection()
    
    if app_works:
        logger.info("✅ Flask app connection works!")
    else:
        logger.error("❌ Flask app connection failed")
        logger.info("Attempting to apply fix...")
        
        if apply_ssl_fix():
            logger.info("✅ Fix applied successfully!")
        else:
            logger.error("❌ Fix failed")
            return False
    
    logger.info("\n" + "=" * 60)
    logger.info("🎉 SSL Connection Diagnostic Complete!")
    logger.info("💡 Recommendations:")
    logger.info(f"   - Use SSL mode: {working_ssl_mode}")
    logger.info(f"   - Use configuration: {working_config['name']}")
    logger.info("   - Enable connection keepalives")
    logger.info("   - Use pool_pre_ping=True")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
