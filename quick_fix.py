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
        
        print("🔧 Running comprehensive column checks...")
        
        # Define all potentially missing columns
        missing_columns_checks = [
            # Orders table
            ("orders", "order_counter", "INTEGER"),
            ("orders", "last_edited_at", "TIMESTAMP"),
            ("orders", "last_edited_by", "INTEGER"),
            ("orders", "edit_count", "INTEGER DEFAULT 0"),
            ("orders", "cleared_from_waiter_requests", "BOOLEAN DEFAULT FALSE"),
            
            # Order Items table
            ("order_items", "special_requests", "TEXT"),
            ("order_items", "is_new", "BOOLEAN DEFAULT TRUE"),
            ("order_items", "is_deleted", "BOOLEAN DEFAULT FALSE"),
            ("order_items", "modifiers_total_price", "NUMERIC(10, 2) DEFAULT 0.00"),
            
            # User Branch Assignments table
            ("user_branch_assignments", "id", "SERIAL PRIMARY KEY"),
            ("user_branch_assignments", "user_id", "INTEGER"),
            ("user_branch_assignments", "branch_id", "INTEGER"),
            ("user_branch_assignments", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            
            # Order Edit History table
            ("order_edit_history", "id", "SERIAL PRIMARY KEY"),
            ("order_edit_history", "order_id", "INTEGER"),
            ("order_edit_history", "edited_by", "INTEGER"),
            ("order_edit_history", "edited_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("order_edit_history", "original_total", "NUMERIC(10,2)"),
            ("order_edit_history", "new_total", "NUMERIC(10,2)"),
            ("order_edit_history", "changes_summary", "TEXT"),
            
            # App Settings table
            ("app_settings", "id", "SERIAL PRIMARY KEY"),
            ("app_settings", "key", "VARCHAR(128) UNIQUE"),
            ("app_settings", "value", "TEXT"),
            ("app_settings", "description", "TEXT"),
            ("app_settings", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("app_settings", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            
            # Admin Pin Codes table
            ("admin_pin_codes", "id", "SERIAL PRIMARY KEY"),
            ("admin_pin_codes", "admin_id", "INTEGER"),
            ("admin_pin_codes", "branch_id", "INTEGER"),
            ("admin_pin_codes", "pin_code_hash", "VARCHAR(128)"),
            ("admin_pin_codes", "pin_type", "VARCHAR(50) DEFAULT 'waiter_assignment'"),
            ("admin_pin_codes", "admin_name", "VARCHAR(100)"),
            ("admin_pin_codes", "is_active", "BOOLEAN DEFAULT TRUE"),
            ("admin_pin_codes", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("admin_pin_codes", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("admin_pin_codes", "pin_code", "VARCHAR(4)"),
            
            # Cashier Pins table
            ("cashier_pins", "id", "SERIAL PRIMARY KEY"),
            ("cashier_pins", "cashier_id", "INTEGER"),
            ("cashier_pins", "branch_id", "INTEGER"),
            ("cashier_pins", "pin_code_hash", "VARCHAR(128)"),
            ("cashier_pins", "is_active", "BOOLEAN DEFAULT TRUE"),
            ("cashier_pins", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("cashier_pins", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            
            # Waiter Cashier Assignments table
            ("waiter_cashier_assignments", "id", "SERIAL PRIMARY KEY"),
            ("waiter_cashier_assignments", "waiter_id", "INTEGER"),
            ("waiter_cashier_assignments", "branch_id", "INTEGER"),
            ("waiter_cashier_assignments", "assigned_cashier_id", "INTEGER"),
            ("waiter_cashier_assignments", "assigned_by_cashier_id", "INTEGER"),
            ("waiter_cashier_assignments", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("waiter_cashier_assignments", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            
            # Manual Card Payments table
            ("manual_card_payments", "id", "SERIAL PRIMARY KEY"),
            ("manual_card_payments", "amount", "NUMERIC(10,2)"),
            ("manual_card_payments", "date", "DATE DEFAULT CURRENT_DATE"),
            ("manual_card_payments", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("manual_card_payments", "branch_id", "INTEGER"),
            ("manual_card_payments", "cashier_id", "INTEGER"),
            ("manual_card_payments", "notes", "TEXT"),
        ]
        
        success_count = 0
        
        for table_name, column_name, column_type in missing_columns_checks:
            try:
                # Check if column exists
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND column_name = %s
                """, (table_name, column_name))
                
                result = cursor.fetchone()
                
                if not result:
                    print(f"➕ Adding missing {table_name}.{column_name}...")
                    
                    # Handle special cases for primary keys
                    if "SERIAL PRIMARY KEY" in column_type:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    else:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    
                    conn.commit()
                    print(f"✅ Added {table_name}.{column_name}")
                    success_count += 1
                else:
                    print(f"✅ {table_name}.{column_name} already exists")
                    
            except Exception as e:
                print(f"⚠️  Could not add {table_name}.{column_name}: {e}")
                conn.rollback()
        
        print(f"🎉 Column check completed! Added {success_count} missing columns.")
        
        # Also ensure all tables exist
        print("🔧 Ensuring all tables exist...")
        
        # Create any missing tables
        table_creation_queries = [
            """
            CREATE TABLE IF NOT EXISTS user_branch_assignments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                branch_id INTEGER REFERENCES branches(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, branch_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS order_edit_history (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id),
                edited_by INTEGER REFERENCES users(id),
                edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                original_total NUMERIC(10,2),
                new_total NUMERIC(10,2),
                changes_summary TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                id SERIAL PRIMARY KEY,
                key VARCHAR(128) UNIQUE NOT NULL,
                value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_pin_codes (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER REFERENCES users(id),
                branch_id INTEGER REFERENCES branches(id),
                pin_code_hash VARCHAR(128),
                pin_type VARCHAR(50) DEFAULT 'waiter_assignment',
                admin_name VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pin_code VARCHAR(4)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cashier_pins (
                id SERIAL PRIMARY KEY,
                cashier_id INTEGER REFERENCES users(id),
                branch_id INTEGER REFERENCES branches(id),
                pin_code_hash VARCHAR(128),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cashier_id, branch_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS waiter_cashier_assignments (
                id SERIAL PRIMARY KEY,
                waiter_id INTEGER REFERENCES users(id),
                branch_id INTEGER REFERENCES branches(id),
                assigned_cashier_id INTEGER REFERENCES users(id),
                assigned_by_cashier_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(waiter_id, branch_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS manual_card_payments (
                id SERIAL PRIMARY KEY,
                amount NUMERIC(10,2) NOT NULL,
                date DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                branch_id INTEGER REFERENCES branches(id),
                cashier_id INTEGER REFERENCES users(id),
                notes TEXT
            )
            """
        ]
        
        for query in table_creation_queries:
            try:
                cursor.execute(query)
                conn.commit()
            except Exception as e:
                print(f"⚠️  Table creation issue (may already exist): {e}")
                conn.rollback()
        
        print("✅ All tables verified/created")
        
        cursor.close()
        conn.close()
        
        print("🎉 Database fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")
        return False

if __name__ == '__main__':
    quick_fix_database()
