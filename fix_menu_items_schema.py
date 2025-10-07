#!/usr/bin/env python3
"""
Fix MenuItem schema - update column sizes to match the model
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from config import Config
from sqlalchemy import text

def fix_menu_items_schema():
    """Fix the menu_items table column sizes"""
    print("🔧 Fixing menu_items table schema...")
    
    app = create_app(Config)
    
    with app.app_context():
        try:
            # Check if menu_items table exists
            result = db.session.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'menu_items' 
                AND column_name IN ('card_color', 'size_flag', 'portion_type', 'visual_priority')
                ORDER BY column_name;
            """)).fetchall()
            
            print("Current column definitions:")
            for row in result:
                print(f"  {row[0]}: {row[1]}({row[2]})")
            
            # Fix column sizes to match the model
            migrations = [
                "ALTER TABLE menu_items ALTER COLUMN card_color TYPE VARCHAR(20);",
                "ALTER TABLE menu_items ALTER COLUMN size_flag TYPE VARCHAR(10);", 
                "ALTER TABLE menu_items ALTER COLUMN portion_type TYPE VARCHAR(20);",
                "ALTER TABLE menu_items ALTER COLUMN visual_priority TYPE VARCHAR(10);"
            ]
            
            print("\n🔄 Applying schema fixes...")
            for migration in migrations:
                try:
                    db.session.execute(text(migration))
                    print(f"✅ {migration}")
                except Exception as e:
                    print(f"⚠️  {migration} - {str(e)}")
            
            db.session.commit()
            
            # Verify the changes
            result = db.session.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'menu_items' 
                AND column_name IN ('card_color', 'size_flag', 'portion_type', 'visual_priority')
                ORDER BY column_name;
            """)).fetchall()
            
            print("\nUpdated column definitions:")
            for row in result:
                print(f"  {row[0]}: {row[1]}({row[2]})")
            
            print("✅ Schema fix completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Schema fix failed: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = fix_menu_items_schema()
    if success:
        print("\n🎉 You can now run the initialization again!")
    else:
        print("\n💥 Schema fix failed. Please check the errors above.")
