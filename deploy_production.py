#!/usr/bin/env python3
"""
Production deployment script for Restaurant POS on Render
Handles database initialization and migration
"""

import os
import sys
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_environment():
    """Check if all required environment variables are set"""
    required_vars = [
        'DATABASE_URL',
        'SECRET_KEY',
        'FLASK_ENV'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    logger.info("All required environment variables are set")
    return True

def initialize_database():
    """Initialize PostgreSQL database with tables and initial data"""
    try:
        from app import create_app, db
        from app.db_init import init_multibranch_db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("Initializing PostgreSQL database...")
            
            # Create all tables
            db.create_all()
            logger.info("Database tables created successfully")
            
            # Initialize with default data
            init_multibranch_db(app)
            logger.info("Database initialized with default data")
            
            return True
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

def run_health_check():
    """Run basic health checks"""
    try:
        from app import create_app
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            from app import db
            from sqlalchemy import text
            
            # Test database connection
            db.session.execute(text('SELECT 1'))
            logger.info("Database connection test passed")
            
            # Check if tables exist
            from app.models import User, Branch
            user_count = User.query.count()
            branch_count = Branch.query.count()
            
            logger.info(f"Database health check: {user_count} users, {branch_count} branches")
            
            return True
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

def main():
    """Main deployment process"""
    logger.info("Starting Restaurant POS production deployment")
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    # Initialize database
    if not initialize_database():
        logger.error("Database initialization failed")
        sys.exit(1)
    
    # Run health check
    if not run_health_check():
        logger.error("Health check failed")
        sys.exit(1)
    
    logger.info("Production deployment completed successfully")
    logger.info("Restaurant POS is ready for production use")

if __name__ == '__main__':
    main()
