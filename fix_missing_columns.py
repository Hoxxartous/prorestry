#!/usr/bin/env python3
"""
Fix missing database columns for production deployment
"""

import os
import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_missing_columns():
    """Add missing columns to the database"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("Checking and fixing missing database columns...")
            
            # Check if order_counter column exists
            try:
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'orders' AND column_name = 'order_counter'
                """)).fetchone()
                
                if not result:
                    logger.info("Adding missing order_counter column to orders table...")
                    db.session.execute(text("""
                        ALTER TABLE orders 
                        ADD COLUMN order_counter INTEGER
                    """))
                    
                    # Create index for better performance
                    db.session.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_orders_order_counter 
                        ON orders(order_counter)
                    """))
                    
                    db.session.commit()
                    logger.info("✅ Added order_counter column successfully")
                else:
                    logger.info("✅ order_counter column already exists")
                    
            except Exception as e:
                logger.error(f"Error checking/adding order_counter column: {e}")
                db.session.rollback()
            
            # Check for other potentially missing columns
            missing_columns_fixes = [
                {
                    'table': 'orders',
                    'column': 'last_edited_at',
                    'type': 'TIMESTAMP',
                    'sql': 'ALTER TABLE orders ADD COLUMN last_edited_at TIMESTAMP'
                },
                {
                    'table': 'orders',
                    'column': 'last_edited_by',
                    'type': 'INTEGER',
                    'sql': 'ALTER TABLE orders ADD COLUMN last_edited_by INTEGER REFERENCES users(id)'
                },
                {
                    'table': 'orders',
                    'column': 'edit_count',
                    'type': 'INTEGER',
                    'sql': 'ALTER TABLE orders ADD COLUMN edit_count INTEGER DEFAULT 0'
                },
                {
                    'table': 'orders',
                    'column': 'cleared_from_waiter_requests',
                    'type': 'BOOLEAN',
                    'sql': 'ALTER TABLE orders ADD COLUMN cleared_from_waiter_requests BOOLEAN DEFAULT FALSE'
                },
                {
                    'table': 'order_items',
                    'column': 'special_requests',
                    'type': 'TEXT',
                    'sql': 'ALTER TABLE order_items ADD COLUMN special_requests TEXT'
                },
                {
                    'table': 'order_items',
                    'column': 'is_new',
                    'type': 'BOOLEAN',
                    'sql': 'ALTER TABLE order_items ADD COLUMN is_new BOOLEAN DEFAULT TRUE'
                },
                {
                    'table': 'order_items',
                    'column': 'is_deleted',
                    'type': 'BOOLEAN',
                    'sql': 'ALTER TABLE order_items ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE'
                }
            ]
            
            for fix in missing_columns_fixes:
                try:
                    result = db.session.execute(text(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = '{fix['table']}' AND column_name = '{fix['column']}'
                    """)).fetchone()
                    
                    if not result:
                        logger.info(f"Adding missing {fix['column']} column to {fix['table']} table...")
                        db.session.execute(text(fix['sql']))
                        db.session.commit()
                        logger.info(f"✅ Added {fix['column']} column successfully")
                    else:
                        logger.info(f"✅ {fix['column']} column already exists")
                        
                except Exception as e:
                    logger.warning(f"Could not add {fix['column']} column: {e}")
                    db.session.rollback()
            
            # Ensure order_counters table exists
            try:
                result = db.session.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_name = 'order_counters'
                """)).fetchone()
                
                if not result:
                    logger.info("Creating order_counters table...")
                    db.session.execute(text("""
                        CREATE TABLE order_counters (
                            id SERIAL PRIMARY KEY,
                            branch_id INTEGER NOT NULL REFERENCES branches(id),
                            current_counter INTEGER DEFAULT 0 NOT NULL,
                            last_reset_date DATE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(branch_id)
                        )
                    """))
                    db.session.commit()
                    logger.info("✅ Created order_counters table successfully")
                else:
                    logger.info("✅ order_counters table already exists")
                    
            except Exception as e:
                logger.error(f"Error with order_counters table: {e}")
                db.session.rollback()
            
            logger.info("Database column fixes completed successfully")
            return True
            
    except Exception as e:
        logger.error(f"Failed to fix database columns: {e}")
        return False

if __name__ == '__main__':
    success = fix_missing_columns()
    sys.exit(0 if success else 1)
