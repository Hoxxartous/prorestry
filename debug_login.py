#!/usr/bin/env python3
"""
Debug script to test login functionality and database connection
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, UserRole
from config import Config

def test_database_connection():
    """Test database connection and user verification"""
    print("🔍 Testing database connection and login functionality...")
    
    app = create_app(Config)
    
    with app.app_context():
        try:
            # Test database connection
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"✅ Database connected. Found {len(tables)} tables: {tables}")
            
            # Test direct SQL query
            result = db.session.execute(text("SELECT COUNT(*) FROM users")).scalar()
            print(f"✅ Direct SQL query successful. User count: {result}")
            
            # Test User model query
            users = User.query.all()
            print(f"✅ User model query successful. Found {len(users)} users:")
            
            for user in users:
                print(f"   • {user.username} (Role: {user.role.value}, Active: {user.is_active})")
                
                # Test password verification for superadmin
                if user.username == 'superadmin':
                    test_passwords = ['SuperAdmin123!', 'superadmin123', 'admin123']
                    for test_pwd in test_passwords:
                        is_valid = user.check_password(test_pwd)
                        print(f"     Password '{test_pwd}': {'✅ VALID' if is_valid else '❌ INVALID'}")
            
            # Test specific superadmin lookup
            superadmin = User.query.filter_by(username='superadmin').first()
            if superadmin:
                print(f"✅ Superadmin found: {superadmin.username}")
                print(f"   • Password hash: {superadmin.password_hash[:20]}...")
                print(f"   • Is active: {superadmin.is_active}")
                print(f"   • Role: {superadmin.role.value}")
                
                # Test password verification
                correct_pwd = superadmin.check_password('SuperAdmin123!')
                print(f"   • Password 'SuperAdmin123!' check: {'✅ VALID' if correct_pwd else '❌ INVALID'}")
            else:
                print("❌ Superadmin user not found!")
                
        except Exception as e:
            print(f"❌ Database test failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_database_connection()
