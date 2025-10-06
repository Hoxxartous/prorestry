#!/usr/bin/env python3
"""
Deployment script for Restaurant POS on Render with PostgreSQL
Handles database setup, migrations, and performance optimization
"""

import os
import sys
import subprocess
import logging
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
    from app import create_app as app_factory
    from config import config
    
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = app_factory(config_name)
    
    return app

def setup_database():
    """Initialize and migrate database"""
    logger.info("🗄️  Setting up PostgreSQL database...")
    
    app = create_app()
    
    with app.app_context():
        from flask_migrate import Migrate
        from app import db
        
        # Initialize Flask-Migrate if not already done
        migrate = Migrate(app, db)
        
        try:
            # Check if migrations directory exists
            if not os.path.exists('migrations'):
                logger.info("📁 Initializing database migrations...")
                init()
            
            # Create migration if needed
            logger.info("📝 Creating database migration...")
            try:
                flask_migrate(message='Deploy to PostgreSQL')
            except Exception as e:
                logger.warning(f"Migration creation warning: {e}")
            
            # Apply migrations
            logger.info("🚀 Applying database migrations...")
            upgrade()
            
            # Create initial data if needed
            create_initial_data(db)
            
            logger.info("✅ Database setup completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            sys.exit(1)

def create_initial_data(db):
    """Create initial data for the restaurant POS system"""
    logger.info("🏪 Creating initial restaurant data...")
    
    try:
        from app.models import Role, Branch, User, Category, MenuItem
        
        # Create roles if they don't exist
        roles = ['SUPER_ADMIN', 'ADMIN', 'CASHIER', 'WAITER']
        for role_name in roles:
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name)
                db.session.add(role)
                logger.info(f"Created role: {role_name}")
        
        # Create default branch if it doesn't exist
        branch = Branch.query.filter_by(name='Main Branch').first()
        if not branch:
            branch = Branch(
                name='Main Branch',
                address='123 Restaurant Street',
                phone='+974-1234-5678'
            )
            db.session.add(branch)
            logger.info("Created default branch: Main Branch")
        
        db.session.commit()
        
        # Create super admin user if it doesn't exist
        super_admin_role = Role.query.filter_by(name='SUPER_ADMIN').first()
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user and super_admin_role:
            admin_user = User(
                username='admin',
                email='admin@restaurant.com',
                role_id=super_admin_role.id,
                branch_id=branch.id,
                is_active=True
            )
            admin_user.set_password('admin123')  # Change this password!
            db.session.add(admin_user)
            logger.info("Created default admin user (username: admin, password: admin123)")
            logger.warning("⚠️  Please change the default admin password after first login!")
        
        # Create sample categories if none exist
        if Category.query.count() == 0:
            categories = [
                {'name': 'Appetizers', 'description': 'Starter dishes'},
                {'name': 'Main Courses', 'description': 'Main dishes'},
                {'name': 'Beverages', 'description': 'Drinks and beverages'},
                {'name': 'Desserts', 'description': 'Sweet treats'}
            ]
            
            for cat_data in categories:
                category = Category(
                    name=cat_data['name'],
                    description=cat_data['description'],
                    branch_id=branch.id
                )
                db.session.add(category)
                logger.info(f"Created category: {cat_data['name']}")
        
        db.session.commit()
        logger.info("✅ Initial data created successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to create initial data: {e}")
        db.session.rollback()

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

def verify_deployment():
    """Verify that the deployment is working correctly"""
    logger.info("🔍 Verifying deployment...")
    
    app = create_app()
    
    with app.app_context():
        from app import db
        from app.models import User, Role, Branch
        
        try:
            # Test database connection
            user_count = User.query.count()
            role_count = Role.query.count()
            branch_count = Branch.query.count()
            
            logger.info(f"📊 Database verification:")
            logger.info(f"   • Users: {user_count}")
            logger.info(f"   • Roles: {role_count}")
            logger.info(f"   • Branches: {branch_count}")
            
            if user_count > 0 and role_count > 0 and branch_count > 0:
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
    logger.info("🚀 Starting Restaurant POS deployment to Render...")
    logger.info("🐘 PostgreSQL + 🔥 Maximum Performance Configuration")
    
    try:
        # Setup environment
        setup_environment()
        
        # Setup database
        setup_database()
        
        # Apply optimizations
        optimize_for_production()
        
        # Verify deployment
        if verify_deployment():
            logger.info("🎉 Deployment completed successfully!")
            logger.info("🌐 Your Restaurant POS is ready for production!")
            logger.info("📱 Access your application at your Render URL")
            logger.info("🔐 Default login: admin / admin123 (please change!)")
        else:
            logger.error("❌ Deployment verification failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
