#!/usr/bin/env python3
"""
Quick fix for missing theme_preference column in users table
This script specifically addresses the deployment error on Render
"""

import os
import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_theme_preference_column():
    """Add missing theme_preference column to users table"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("🔍 Checking for missing theme_preference column in users table...")
            
            # Check if theme_preference column exists
            try:
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'theme_preference'
                """)).fetchone()
                
                if not result:
                    logger.info("➕ Adding missing theme_preference column to users table...")
                    
                    # Add the theme_preference column with default value
                    db.session.execute(text("""
                        ALTER TABLE users 
                        ADD COLUMN theme_preference VARCHAR(32) DEFAULT 'dark' NOT NULL
                    """))
                    
                    db.session.commit()
                    logger.info("✅ Successfully added theme_preference column with default 'dark'")
                    
                    # Verify the column was added
                    verify_result = db.session.execute(text("""
                        SELECT column_name, data_type, column_default, is_nullable
                        FROM information_schema.columns 
                        WHERE table_name = 'users' AND column_name = 'theme_preference'
                    """)).fetchone()
                    
                    if verify_result:
                        logger.info(f"✅ Verification successful: {verify_result}")
                    else:
                        logger.error("❌ Verification failed - column not found after creation")
                        return False
                        
                else:
                    logger.info("✅ theme_preference column already exists")
                    
                return True
                    
            except Exception as e:
                logger.error(f"❌ Error checking/adding theme_preference column: {e}")
                db.session.rollback()
                return False
            
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("🚀 Starting theme_preference column fix for Restaurant POS")
    
    success = fix_theme_preference_column()
    
    if success:
        logger.info("🎉 Theme preference column fix completed successfully!")
        logger.info("💡 Your app should now deploy without the theme_preference error")
        return True
    else:
        logger.error("💥 Theme preference column fix failed")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
