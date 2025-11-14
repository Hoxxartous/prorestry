#!/usr/bin/env python3
"""
Quick Render Fix - Run this in Render console
============================================

This is a simplified version that can be run directly in the Render console.
It fixes the two main issues:
1. Creates the missing email_configurations table
2. Fixes any users with invalid role values
"""

import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def main():
    print("🚀 Starting quick Render fixes...")
    
    try:
        # Get database URL
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found")
            return
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        print("✅ Connected to database")
        
        # 1. Create email_configurations table
        print("📧 Creating email_configurations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_configurations (
                id SERIAL PRIMARY KEY,
                mail_server VARCHAR(255) NOT NULL,
                mail_port INTEGER NOT NULL,
                mail_username VARCHAR(255) NOT NULL,
                mail_password VARCHAR(255) NOT NULL,
                mail_default_sender VARCHAR(255) NOT NULL,
                mail_use_tls BOOLEAN DEFAULT TRUE,
                mail_use_ssl BOOLEAN DEFAULT FALSE,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE NOT NULL
            );
        """)
        print("✅ email_configurations table created")
        
        # 2. Fix UserRole enum values
        print("👤 Fixing user roles...")
        
        # Add missing enum values if they don't exist
        enum_values = ['super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen']
        for value in enum_values:
            try:
                cursor.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{value}';")
            except:
                pass  # Value might already exist
        
        # Fix any users with uppercase role values
        role_mappings = {
            'IT_ADMIN': 'it_admin',
            'SUPER_USER': 'super_user', 
            'BRANCH_ADMIN': 'branch_admin',
            'MANAGER': 'manager',
            'CASHIER': 'cashier',
            'WAITER': 'waiter',
            'KITCHEN': 'kitchen'
        }
        
        for old_role, new_role in role_mappings.items():
            cursor.execute(
                "UPDATE users SET role = %s WHERE role = %s;",
                (new_role, old_role)
            )
            cursor.execute("SELECT ROW_COUNT();")
            count = cursor.rowcount
            if count > 0:
                print(f"✅ Fixed {count} users: {old_role} -> {new_role}")
        
        # 3. Verify fixes
        print("🔍 Verifying fixes...")
        
        # Check email_configurations table
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'email_configurations');")
        if cursor.fetchone()[0]:
            print("✅ email_configurations table exists")
        else:
            print("❌ email_configurations table missing")
        
        # Check for invalid user roles
        cursor.execute("""
            SELECT COUNT(*) FROM users 
            WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
        """)
        invalid_count = cursor.fetchone()[0]
        if invalid_count == 0:
            print("✅ All user roles are valid")
        else:
            print(f"⚠️ Found {invalid_count} users with invalid roles")
        
        cursor.close()
        conn.close()
        print("🎉 Quick fixes completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
