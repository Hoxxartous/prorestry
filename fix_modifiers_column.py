#!/usr/bin/env python3
"""
Emergency fix for the modifiers_total_price column issue
This script specifically addresses the PostgreSQL error with invalid default value syntax
"""

import os
import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_modifiers_column():
    """Fix the modifiers_total_price column with correct default value"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("Fixing modifiers_total_price column...")
            
            # Check if the column already exists
            try:
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'order_items' AND column_name = 'modifiers_total_price'
                """)).fetchone()
                
                if result:
                    logger.info("✅ modifiers_total_price column already exists")
                    return True
                
                # Add the column with correct syntax
                logger.info("Adding modifiers_total_price column with correct default value...")
                db.session.execute(text("""
                    ALTER TABLE order_items 
                    ADD COLUMN modifiers_total_price NUMERIC(10, 2) DEFAULT 0.00
                """))
                
                db.session.commit()
                logger.info("✅ Successfully added modifiers_total_price column")
                
                # Verify the column was added
                result = db.session.execute(text("""
                    SELECT column_name, column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'order_items' AND column_name = 'modifiers_total_price'
                """)).fetchone()
                
                if result:
                    logger.info(f"✅ Column verified: {result[0]} with default: {result[1]}")
                else:
                    logger.error("❌ Column verification failed")
                    return False
                
                return True
                
            except Exception as e:
                logger.error(f"Error fixing modifiers_total_price column: {e}")
                db.session.rollback()
                return False
            
    except Exception as e:
        logger.error(f"Failed to fix modifiers_total_price column: {e}")
        return False

if __name__ == '__main__':
    success = fix_modifiers_column()
    if success:
        print("🎉 modifiers_total_price column fix completed successfully!")
    else:
        print("❌ Failed to fix modifiers_total_price column")
    sys.exit(0 if success else 1)
