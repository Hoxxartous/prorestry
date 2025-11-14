#!/usr/bin/env python3
"""
Fix Render Deployment Issues Script
==================================

This script fixes two critical issues in the Render deployment:
1. Missing email_configurations table
2. UserRole enum mismatch (IT_ADMIN vs it_admin)

Run this script after deployment to fix database issues.
"""

import os
import sys
import logging
from datetime import datetime
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_database_url():
    """Get database URL from environment variables"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not found")
        sys.exit(1)
    return database_url

def create_email_configurations_table(cursor):
    """Create the missing email_configurations table"""
    logger.info("Creating email_configurations table...")
    
    create_table_sql = """
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
    """
    
    try:
        cursor.execute(create_table_sql)
        logger.info("✅ email_configurations table created successfully")
        
        # Create index for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_configurations_active ON email_configurations(is_active);")
        logger.info("✅ Index created for email_configurations table")
        
    except Exception as e:
        logger.error(f"❌ Failed to create email_configurations table: {e}")
        raise

def fix_userrole_enum(cursor):
    """Fix the UserRole enum to include proper values"""
    logger.info("Checking and fixing UserRole enum...")
    
    try:
        # First, check if the enum exists and what values it has
        cursor.execute("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (
                SELECT oid 
                FROM pg_type 
                WHERE typname = 'userrole'
            );
        """)
        
        existing_values = [row[0] for row in cursor.fetchall()]
        logger.info(f"Current UserRole enum values: {existing_values}")
        
        # Define the expected values (lowercase as per the Python enum)
        expected_values = [
            'super_user',
            'it_admin', 
            'branch_admin',
            'manager',
            'cashier',
            'waiter',
            'kitchen'
        ]
        
        # Add missing enum values
        for value in expected_values:
            if value not in existing_values:
                try:
                    cursor.execute(f"ALTER TYPE userrole ADD VALUE '{value}';")
                    logger.info(f"✅ Added '{value}' to UserRole enum")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"ℹ️ Value '{value}' already exists in UserRole enum")
                    else:
                        logger.error(f"❌ Failed to add '{value}' to UserRole enum: {e}")
        
        # Check if there are any users with invalid role values and fix them
        cursor.execute("""
            SELECT id, username, role 
            FROM users 
            WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
        """)
        
        invalid_users = cursor.fetchall()
        if invalid_users:
            logger.warning(f"Found {len(invalid_users)} users with invalid role values")
            for user_id, username, role in invalid_users:
                logger.warning(f"User {username} (ID: {user_id}) has invalid role: {role}")
                
                # Map common invalid values to correct ones
                role_mapping = {
                    'IT_ADMIN': 'it_admin',
                    'SUPER_USER': 'super_user',
                    'BRANCH_ADMIN': 'branch_admin',
                    'MANAGER': 'manager',
                    'CASHIER': 'cashier',
                    'WAITER': 'waiter',
                    'KITCHEN': 'kitchen'
                }
                
                if role in role_mapping:
                    new_role = role_mapping[role]
                    cursor.execute(
                        "UPDATE users SET role = %s WHERE id = %s;",
                        (new_role, user_id)
                    )
                    logger.info(f"✅ Fixed user {username}: {role} -> {new_role}")
                else:
                    # Default to cashier for unknown roles
                    cursor.execute(
                        "UPDATE users SET role = 'cashier' WHERE id = %s;",
                        (user_id,)
                    )
                    logger.info(f"✅ Fixed user {username}: {role} -> cashier (default)")
        
    except Exception as e:
        logger.error(f"❌ Failed to fix UserRole enum: {e}")
        raise

def create_updated_at_trigger(cursor):
    """Create trigger to automatically update updated_at timestamp"""
    logger.info("Creating updated_at trigger for email_configurations...")
    
    try:
        # Create the trigger function if it doesn't exist
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        
        # Create the trigger
        cursor.execute("""
            DROP TRIGGER IF EXISTS update_email_configurations_updated_at ON email_configurations;
            CREATE TRIGGER update_email_configurations_updated_at
                BEFORE UPDATE ON email_configurations
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)
        
        logger.info("✅ Updated_at trigger created successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to create updated_at trigger: {e}")
        raise

def verify_fixes(cursor):
    """Verify that all fixes have been applied correctly"""
    logger.info("Verifying fixes...")
    
    try:
        # Check if email_configurations table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'email_configurations'
            );
        """)
        
        table_exists = cursor.fetchone()[0]
        if table_exists:
            logger.info("✅ email_configurations table exists")
        else:
            logger.error("❌ email_configurations table does not exist")
            return False
        
        # Check UserRole enum values
        cursor.execute("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (
                SELECT oid 
                FROM pg_type 
                WHERE typname = 'userrole'
            )
            ORDER BY enumlabel;
        """)
        
        enum_values = [row[0] for row in cursor.fetchall()]
        expected_values = ['branch_admin', 'cashier', 'it_admin', 'kitchen', 'manager', 'super_user', 'waiter']
        
        missing_values = set(expected_values) - set(enum_values)
        if missing_values:
            logger.error(f"❌ Missing UserRole enum values: {missing_values}")
            return False
        else:
            logger.info("✅ All required UserRole enum values are present")
        
        # Check for users with invalid roles
        cursor.execute("""
            SELECT COUNT(*) 
            FROM users 
            WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
        """)
        
        invalid_count = cursor.fetchone()[0]
        if invalid_count > 0:
            logger.error(f"❌ Found {invalid_count} users with invalid role values")
            return False
        else:
            logger.info("✅ All users have valid role values")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to verify fixes: {e}")
        return False

def main():
    """Main function to run all fixes"""
    logger.info("🚀 Starting Render deployment fixes...")
    
    try:
        # Get database connection
        database_url = get_database_url()
        logger.info("Connecting to database...")
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        logger.info("✅ Database connection successful")
        
        # Apply fixes
        create_email_configurations_table(cursor)
        fix_userrole_enum(cursor)
        create_updated_at_trigger(cursor)
        
        # Verify fixes
        if verify_fixes(cursor):
            logger.info("🎉 All fixes applied and verified successfully!")
        else:
            logger.error("❌ Some fixes failed verification")
            sys.exit(1)
        
        # Close connection
        cursor.close()
        conn.close()
        
        logger.info("✅ Database connection closed")
        logger.info("🎉 Render deployment fixes completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to apply fixes: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
