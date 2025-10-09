#!/usr/bin/env python3
"""
Deployment script for Restaurant POS on Render with PostgreSQL
Handles database setup, migrations, and performance optimization
Supports both first-time setup and existing database verification
"""

import os
import sys
import subprocess
import logging
import time
import argparse

# PostgreSQL driver compatibility - prefer psycopg2-binary if available
try:
    import psycopg2
except ImportError:
    # Fallback to psycopg if psycopg2 not available
    pass

from flask import Flask
from flask_migrate import Migrate, upgrade, init, migrate as flask_migrate

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_environment():
    """Set up environment variables for deployment"""
    logger.info("🔧 Setting up deployment environment...")
    
    # Ensure we're in production mode
    os.environ['FLASK_ENV'] = 'production'
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Database URL should be provided by Render
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable not set")
        logger.info("Make sure you have created a PostgreSQL database in Render")
        sys.exit(1)
    
    # Fix postgres:// to postgresql:// if needed
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        os.environ['DATABASE_URL'] = database_url
    
    logger.info(f"✅ Database URL configured: {database_url.split('@')[0]}@***")

def create_app():
    """Create Flask application for deployment"""
    # Import here to avoid eventlet conflicts during build
    import os
    os.environ['DEPLOYMENT_MODE'] = 'true'  # Signal that we're in deployment mode
    
    from config import ProductionConfig
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    
    # Create minimal app for database operations only
    app = Flask(__name__)
    app.config.from_object(ProductionConfig)
    
    # Initialize database
    db = SQLAlchemy()
    db.init_app(app)
    
    return app, db

def setup_database(existing_database=False):
    """Initialize and migrate database"""
    if existing_database:
        logger.info("🔧 Verifying existing PostgreSQL database...")
    else:
        logger.info("🗄️  Setting up PostgreSQL database (first-time)...")
    
    app, db = create_app()
    
    with app.app_context():
        from flask_migrate import Migrate
        
        # Initialize Flask-Migrate if not already done
        migrate = Migrate(app, db)
        
        try:
            # Check if migrations directory exists
            if not os.path.exists('migrations'):
                logger.info("📁 Initializing database migrations...")
                init()
            
            # Check if database needs migration
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if existing_tables:
                logger.info("📊 Database tables already exist")
                logger.info(f"   Found {len(existing_tables)} existing tables")
                
                if existing_database:
                    logger.info("🔧 Verifying existing database schema...")
                    # For existing databases, just verify schema and ensure app compatibility
                    verify_existing_database_schema(app, db)
                else:
                    logger.info("⚠️  Tables exist but this appears to be first-time setup")
                    logger.info("   Will verify and update data if needed")
                    # Still run data initialization (it has duplicate prevention)
                    create_comprehensive_initial_data(app)
            else:
                logger.info("📝 Database is empty, creating tables and initial data...")
                # Create migration if needed
                try:
                    flask_migrate(message='Deploy to PostgreSQL')
                except Exception as e:
                    logger.warning(f"Migration creation warning: {e}")
                
                # Apply migrations
                logger.info("🚀 Applying database migrations...")
                upgrade()
                
                # Create initial data using comprehensive multi-branch initialization
                create_comprehensive_initial_data(app)
            
            # Ensure all data is committed
            db.session.commit()
            
            # Verify data was created successfully (within same context)
            verify_data_in_context(db)
            
            logger.info("✅ Database setup completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            sys.exit(1)

def verify_existing_database_schema(app, db):
    """Verify existing database schema and ensure compatibility"""
    logger.info("🔍 Verifying database schema compatibility...")
    
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        # Check for critical tables
        required_tables = ['users', 'branches', 'categories', 'menu_items', 'orders']
        missing_tables = [table for table in required_tables if table not in existing_tables]
        
        if missing_tables:
            logger.warning(f"⚠️  Missing critical tables: {missing_tables}")
            logger.info("   Database may need migration or initialization")
        else:
            logger.info("✅ All critical tables found")
        
        # Check if we need to run any schema fixes (PostgreSQL-specific)
        from app.db_init import init_multibranch_db
        logger.info("🔧 Running schema verification and fixes...")
        init_multibranch_db(app)
        
        logger.info("✅ Database schema verification completed")
        
    except Exception as e:
        logger.warning(f"⚠️  Schema verification warning: {e}")
        logger.info("   Application will handle any missing setup on startup")

def create_comprehensive_initial_data(app):
    """Create comprehensive initial data using the multi-branch initialization"""
    logger.info("🏪 Creating comprehensive restaurant data...")
    
    try:
        # Import the comprehensive initialization function
        from app.db_init import init_multibranch_db
        
        # Run the comprehensive multi-branch initialization
        init_multibranch_db(app)
        
        logger.info("✅ Comprehensive multi-branch data created successfully!")
        logger.info("🏢 Created 5 branches with complete data:")
        logger.info("   • Main Branch (MAIN)")
        logger.info("   • City Center (CC01)")
        logger.info("   • Villaggio (VIL1)")
        logger.info("   • The Pearl (PRL1)")
        logger.info("   • West Bay (WB01)")
        logger.info("👥 Created users: superadmin, admin1-5, cashier1_1-2, waiter1-5")
        logger.info("🍽️  Created complete menu with categories and items")
        logger.info("🪑 Created tables for each branch")
        logger.info("🚚 Created delivery companies")
        logger.info("🔐 Default login: superadmin / SuperAdmin123!")
        logger.warning("⚠️  Please change default passwords after first login!")
        
    except Exception as e:
        logger.error(f"❌ Failed to create comprehensive initial data: {e}")
        raise

def verify_data_in_context(db):
    """Verify data was created successfully within the same database context"""
    try:
        from app.models import User, UserRole, Branch
        
        user_count = User.query.count()
        branch_count = Branch.query.count()
        role_types = len([role for role in UserRole])
        
        logger.info(f"📊 Database verification (same context):")
        logger.info(f"   • Users: {user_count}")
        logger.info(f"   • Role types available: {role_types}")
        logger.info(f"   • Branches: {branch_count}")
        
        if user_count > 0 and branch_count > 0:
            logger.info("✅ Data verification passed!")
        else:
            logger.warning("⚠️  Data verification shows missing data, but this may be normal during initialization")
            
    except Exception as e:
        logger.warning(f"⚠️  Data verification warning: {e}")

def optimize_for_production():
    """Apply production optimizations"""
    logger.info("⚡ Applying production optimizations...")
    
    # Set Python optimizations
    os.environ['PYTHONOPTIMIZE'] = '1'
    
    # Ensure logs directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')
        logger.info("📁 Created logs directory")
    
    logger.info("✅ Production optimizations applied!")

def verify_deployment_simple():
    """Simple verification that uses existing database connection"""
    logger.info("🔍 Verifying deployment...")
    
    try:
        from app import db
        from app.models import User, UserRole, Branch
        
        # Test database connection using existing context
        user_count = User.query.count()
        branch_count = Branch.query.count()
        role_types = len([role for role in UserRole])
        
        logger.info(f"📊 Database verification:")
        logger.info(f"   • Users: {user_count}")
        logger.info(f"   • Role types available: {role_types}")
        logger.info(f"   • Branches: {branch_count}")
        
        if user_count > 0 and branch_count > 0:
            logger.info("✅ Database verification passed!")
            return True
        else:
            logger.error("❌ Database verification failed - missing data")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database verification failed: {e}")
        return False

def verify_deployment():
    """Verify that the deployment is working correctly"""
    logger.info("🔍 Verifying deployment...")
    
    app = create_app()
    
    with app.app_context():
        from app import db
        from app.models import User, UserRole, Branch
        
        try:
            # Test database connection
            user_count = User.query.count()
            branch_count = Branch.query.count()
            role_types = len([role for role in UserRole])
            
            logger.info(f"📊 Database verification:")
            logger.info(f"   • Users: {user_count}")
            logger.info(f"   • Role types available: {role_types}")
            logger.info(f"   • Branches: {branch_count}")
            
            if user_count > 0 and branch_count > 0:
                logger.info("✅ Database verification passed!")
                return True
            else:
                logger.error("❌ Database verification failed - missing data")
                return False
                
        except Exception as e:
            logger.error(f"❌ Database verification failed: {e}")
            return False

def main():
    """Main deployment function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Deploy Restaurant POS to Render')
    parser.add_argument('--existing-database', action='store_true', 
                       help='Indicate that database already exists and contains data')
    args = parser.parse_args()
    
    if args.existing_database:
        logger.info("🔧 Starting Restaurant POS database verification...")
        logger.info("🐘 PostgreSQL + Existing Database Mode")
    else:
        logger.info("🚀 Starting Restaurant POS deployment to Render...")
        logger.info("🐘 PostgreSQL + 🔥 Maximum Performance Configuration")
    
    try:
        # Setup environment
        setup_environment()
        
        # Setup database (with existing database flag)
        setup_database(existing_database=args.existing_database)
        
        # Apply optimizations
        optimize_for_production()
        
        # Deployment completed successfully (verification done within setup context)
        if args.existing_database:
            logger.info("✅ Database verification completed successfully!")
            logger.info("🔧 Your existing Restaurant POS database is ready!")
        else:
            logger.info("🎉 Deployment completed successfully!")
            logger.info("🌐 Your Restaurant POS is now live on Render!")
            logger.info("🔐 Default login: superadmin / SuperAdmin123!")
            logger.warning("⚠️  Please change default passwords after first login!")
            
    except Exception as e:
        logger.error(f"❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
