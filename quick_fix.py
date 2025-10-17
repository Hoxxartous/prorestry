#!/usr/bin/env python3
"""
Quick fix for the missing order_counter column
Run this if you need to fix the database immediately
"""

import os
import psycopg2
from urllib.parse import urlparse

def quick_fix_database():
    """Quick fix for missing columns"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not set")
        return False
    
    try:
        # Connect directly to PostgreSQL
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("🔧 Checking for missing order_counter column...")
        
        # Check if column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'orders' AND column_name = 'order_counter'
        """)
        
        result = cursor.fetchone()
        
        if not result:
            print("➕ Adding missing order_counter column...")
            cursor.execute("ALTER TABLE orders ADD COLUMN order_counter INTEGER")
            conn.commit()
            print("✅ Added order_counter column successfully!")
        else:
            print("✅ order_counter column already exists")
        
        cursor.close()
        conn.close()
        
        print("🎉 Database fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")
        return False

if __name__ == '__main__':
    quick_fix_database()
