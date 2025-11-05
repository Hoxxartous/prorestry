#!/usr/bin/env python3
"""
Render Deployment Fix Script
Handles all missing columns and schema issues for existing PostgreSQL database
"""

import os
import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_and_add_column(db, table_name, column_name, column_definition):
    """Check if column exists and add it if missing"""
    try:
        # Check if column exists
        result = db.session.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' AND column_name = '{column_name}'
        """)).fetchone()
        
        if not result:
            logger.info(f"➕ Adding missing {column_name} column to {table_name} table...")
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
            db.session.commit()
            logger.info(f"✅ Successfully added {column_name} column")
            return True
        else:
            logger.info(f"✅ {column_name} column already exists in {table_name}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error adding {column_name} to {table_name}: {e}")
        db.session.rollback()
        return False

def fix_all_missing_columns():
    """Fix all potentially missing columns"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("🔍 Checking and fixing all missing database columns...")
            
            # List of all potentially missing columns
            missing_columns = [
                # Users table
                {
                    'table': 'users',
                    'column': 'theme_preference',
                    'definition': "theme_preference VARCHAR(32) DEFAULT 'dark' NOT NULL"
                },
                # Orders table
                {
                    'table': 'orders',
                    'column': 'order_counter',
                    'definition': 'order_counter INTEGER'
                },
                {
                    'table': 'orders',
                    'column': 'last_edited_at',
                    'definition': 'last_edited_at TIMESTAMP'
                },
                {
                    'table': 'orders',
                    'column': 'last_edited_by',
                    'definition': 'last_edited_by INTEGER REFERENCES users(id)'
                },
                {
                    'table': 'orders',
                    'column': 'edit_count',
                    'definition': 'edit_count INTEGER DEFAULT 0'
                },
                {
                    'table': 'orders',
                    'column': 'cleared_from_waiter_requests',
                    'definition': 'cleared_from_waiter_requests BOOLEAN DEFAULT FALSE'
                },
                # Order items table
                {
                    'table': 'order_items',
                    'column': 'special_requests',
                    'definition': 'special_requests TEXT'
                },
                {
                    'table': 'order_items',
                    'column': 'is_new',
                    'definition': 'is_new BOOLEAN DEFAULT FALSE'
                },
                {
                    'table': 'order_items',
                    'column': 'is_deleted',
                    'definition': 'is_deleted BOOLEAN DEFAULT FALSE'
                },
                {
                    'table': 'order_items',
                    'column': 'modifiers_total_price',
                    'definition': 'modifiers_total_price NUMERIC(10, 2) DEFAULT 0.00'
                }
            ]
            
            success_count = 0
            total_count = len(missing_columns)
            
            for column_info in missing_columns:
                if check_and_add_column(
                    db, 
                    column_info['table'], 
                    column_info['column'], 
                    column_info['definition']
                ):
                    success_count += 1
            
            # Create missing indexes
            logger.info("🔍 Creating missing indexes...")
            try:
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_orders_order_counter 
                    ON orders(order_counter)
                """))
                db.session.commit()
                logger.info("✅ Order counter index created")
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
                db.session.rollback()
            
            # Ensure all tables exist
            logger.info("🔍 Ensuring all tables exist...")
            try:
                from app import db as app_db
                app_db.create_all()
                logger.info("✅ All tables verified/created")
            except Exception as e:
                logger.warning(f"Table creation warning: {e}")
            
            logger.info(f"📊 Column fix summary: {success_count}/{total_count} columns processed successfully")
            
            return success_count == total_count
            
    except Exception as e:
        logger.error(f"❌ Failed to fix database columns: {e}")
        return False

def verify_critical_columns():
    """Verify that critical columns now exist"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("🔍 Verifying critical columns...")
            
            # Check theme_preference specifically
            result = db.session.execute(text("""
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'theme_preference'
            """)).fetchone()
            
            if result:
                logger.info(f"✅ theme_preference column verified: {result}")
                return True
            else:
                logger.error("❌ theme_preference column still missing!")
                return False
                
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("🚀 Starting Render Deployment Fix for Restaurant POS")
    logger.info("🎯 This will fix the theme_preference column error and other missing columns")
    
    # Step 1: Fix all missing columns
    if not fix_all_missing_columns():
        logger.error("💥 Failed to fix missing columns")
        return False
    
    # Step 2: Verify critical columns
    if not verify_critical_columns():
        logger.error("💥 Critical column verification failed")
        return False
    
    logger.info("🎉 Render deployment fix completed successfully!")
    logger.info("💡 Your app should now deploy without schema errors")
    logger.info("🔄 Try rebuilding your app on Render now")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
